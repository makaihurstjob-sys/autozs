from datetime import datetime, timedelta
from sqlalchemy import select
from test_listing_jobs import create_ready_product
from app.core.database import get_db
from app.main import app
from app.models.domain import DeliveryCheckJob, SupplierProduct


def enable(client, zips=None):
    response = client.put('/delivery-quotes/policy', json={'enabled': True, 'postal_codes': zips or ['33101', '10001']})
    assert response.status_code == 200


def enqueue(client, product):
    result = client.post('/listing-jobs', json={'product_ids': [product['id']]})
    assert result.status_code == 200
    return result.json()[0]


def claim(client, worker='isolated-1'):
    return client.post('/delivery-quotes/jobs/claim', json={'worker_id': worker}).json()


def complete(client, job, worker='isolated-1', **overrides):
    quote = {'source_url': job['source_url'], 'postal_code': job['postal_code'], 'quantity': 1, 'delivery_charge': 0}
    quote.update(overrides)
    return client.post(f"/delivery-quotes/jobs/{job['id']}/complete", json={
        'worker_id': worker, 'lease_token': job['lease_token'], 'quote': quote, 'cart_cleared': True})


def mutate(client, callback):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    callback(db)
    db.commit()
    generator.close()


def test_disabled_by_default_and_policy_validation(client):
    assert client.get('/delivery-quotes/policy').json()['enabled'] is False
    assert claim(client) is None
    for zips in ([], ['33101', '33101'], ['oops'], ['１２３４５']):
        assert client.put('/delivery-quotes/policy', json={'enabled': True, 'postal_codes': zips}).status_code == 422


def test_listing_waits_then_resumes_when_all_zips_verified(client):
    product = create_ready_product(client)
    enable(client)
    listing = enqueue(client, product)
    assert listing['manual_ready'] is False
    assert len(client.get('/delivery-quotes/jobs').json()) == 2
    assert client.post(f"/listing-jobs/{listing['id']}/run").json()['job']['status'] == 'queued'
    first = claim(client)
    assert complete(client, first).status_code == 200
    assert client.post('/listing-jobs/next').status_code == 404
    second = claim(client)
    assert first['postal_code'] != second['postal_code']
    assert complete(client, second).status_code == 200
    assert client.post('/listing-jobs/next').json()['job']['status'] == 'running'


def test_mismatched_evidence_and_wrong_worker_cannot_complete(client):
    product = create_ready_product(client)
    enable(client, ['33101'])
    enqueue(client, product)
    job = claim(client)
    assert claim(client)['id'] == job['id']
    assert claim(client, 'isolated-2') is None
    for overrides in ({'postal_code': '10001'}, {'quantity': 2}, {'source_url': 'https://www.homedepot.com/p/Other/999999999'}):
        assert complete(client, job, **overrides).status_code == 409
    assert complete(client, job, worker='isolated-2').status_code == 409
    assert client.get(f"/delivery-quotes/products/{product['id']}").json()['quotes'] == []
    assert complete(client, job, delivery_charge=35).status_code == 200
    assert '$35.00' in client.get(f"/delivery-quotes/products/{product['id']}").json()['blocking_reason']


def test_stale_and_changed_source_requeue_checks(client):
    product = create_ready_product(client)
    enable(client, ['33101'])
    listing = enqueue(client, product)
    job = claim(client)
    complete(client, job)
    def age(db):
        db.get(DeliveryCheckJob, job['id']).completed_at = datetime.utcnow() - timedelta(days=2)
    mutate(client, age)
    assert client.post(f"/listing-jobs/{listing['id']}/run").json()['job']['status'] == 'queued'
    refreshed = claim(client)
    assert refreshed['id'] == job['id'] and refreshed['attempts'] == 1
    complete(client, refreshed)
    def replace_source(db):
        db.scalar(select(SupplierProduct)).source_url = 'https://www.homedepot.com/p/New/999999999'
    mutate(client, replace_source)
    assert client.post(f"/listing-jobs/{listing['id']}/run").json()['job']['status'] == 'queued'
    assert claim(client)['source_url'].endswith('999999999')


def test_lease_expiry_backoff_and_bounded_retries(client):
    product = create_ready_product(client)
    enable(client, ['33101'])
    enqueue(client, product)
    for attempt in range(1, 4):
        job = claim(client)
        assert job['attempts'] == attempt
        def expire(db):
            db.get(DeliveryCheckJob, job['id']).lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        mutate(client, expire)
        assert complete(client, job).status_code == 409
        assert claim(client) is None
        def advance_retry(db):
            db.get(DeliveryCheckJob, job['id']).retry_at = datetime.utcnow() - timedelta(seconds=1)
        mutate(client, advance_retry)
    assert claim(client) is None
    assert client.get('/delivery-quotes/jobs').json()[0]['status'] == 'needs_review'


def test_completed_response_can_be_recovered_after_connection_loss(client):
    product = create_ready_product(client)
    enable(client, ['33101'])
    enqueue(client, product)
    job = claim(client)
    complete(client, job)
    response = client.post(f"/delivery-quotes/jobs/{job['id']}/heartbeat", json={
        'worker_id': 'isolated-1', 'lease_token': job['lease_token']})
    assert response.status_code == 200 and response.json()['status'] == 'completed'


def test_missing_quote_at_queue_head_does_not_starve_verified_product(client):
    first = create_ready_product(client)
    second = create_ready_product(client, source_id='987654321')
    enable(client, ['33101'])
    enqueue(client, second)
    complete(client, claim(client))
    # Earlier queue position by scheduled_for, so the unverified item is examined first.
    first_job = enqueue(client, first)
    client.patch(f"/listing-jobs/{first_job['id']}", json={'scheduled_for': '2020-01-01T00:00:00Z'})
    response = client.post('/listing-jobs/next')
    assert response.json()['job']['product_id'] == second['id']


def test_policy_pause_denies_worker_mutation_lease(client):
    product = create_ready_product(client)
    enable(client, ['33101'])
    enqueue(client, product)
    job = claim(client)
    client.put('/delivery-quotes/policy', json={'enabled': False, 'postal_codes': ['33101']})
    assert client.post(f"/delivery-quotes/jobs/{job['id']}/heartbeat", json={
        'worker_id': 'isolated-1', 'lease_token': job['lease_token']}).status_code == 409
    assert complete(client, job).status_code == 409
    assert client.get(f"/delivery-quotes/products/{product['id']}").json()['quotes'] == []


def test_removed_zip_denies_heartbeat_and_completion(client):
    product = create_ready_product(client)
    enable(client, ['33101'])
    enqueue(client, product)
    job = claim(client)
    enable(client, ['10001'])
    assert client.post(f"/delivery-quotes/jobs/{job['id']}/heartbeat", json={
        'worker_id': 'isolated-1', 'lease_token': job['lease_token']}).status_code == 409
    assert complete(client, job).status_code == 409
    assert client.get(f"/delivery-quotes/products/{product['id']}").json()['quotes'] == []


def test_source_change_revokes_browser_action_lease(client):
    product = create_ready_product(client)
    enable(client, ['33101'])
    enqueue(client, product)
    job = claim(client)
    def replace_source(db):
        db.scalar(select(SupplierProduct)).source_url = 'https://www.homedepot.com/p/New/999999999'
    mutate(client, replace_source)
    assert client.post(f"/delivery-quotes/jobs/{job['id']}/heartbeat", json={
        'worker_id': 'isolated-1', 'lease_token': job['lease_token']}).status_code == 409
    assert complete(client, job).status_code == 409
    assert client.get(f"/delivery-quotes/products/{product['id']}").json()['quotes'] == []

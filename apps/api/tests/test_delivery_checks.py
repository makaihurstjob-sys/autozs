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


def test_supplier_failures_back_off_then_exhaust_retry_budget(client):
    product = create_ready_product(client)
    enable(client, ['33101'])
    enqueue(client, product)
    for attempt in range(1, 4):
        job = claim(client)
        assert job['attempts'] == attempt
        response = client.post(f"/delivery-quotes/jobs/{job['id']}/failed", json={
            'worker_id': 'isolated-1', 'lease_token': job['lease_token'],
            'message': 'Transient supplier page error', 'retryable': True})
        assert response.status_code == 200
        assert response.json()['status'] == ('queued' if attempt < 3 else 'needs_review')
        assert claim(client) is None
        def advance_retry(db):
            db.get(DeliveryCheckJob, job['id']).retry_at = datetime.utcnow() - timedelta(seconds=1)
        mutate(client, advance_retry)
    assert claim(client) is None
    assert client.get(f"/delivery-quotes/products/{product['id']}").json()['quotes'] == []
    assert client.post('/listing-jobs/next').status_code == 404
    other = create_ready_product(client, source_id='987654321')
    enqueue(client, other)
    assert claim(client)['source_url'].endswith('987654321')


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


def configure_trial(client, product, zip_code='60601'):
    supplier_ids = []
    mutate(client, lambda db: supplier_ids.append(db.scalar(select(SupplierProduct.id).where(
        SupplierProduct.product_id == product['id']))))
    policy = {'enabled': False, 'postal_codes': ['33101', '10001'],
              'trial': {'supplier_product_id': supplier_ids[0], 'postal_code': zip_code}}
    assert client.put('/delivery-quotes/policy', json=policy).status_code == 200
    return policy


def test_trial_claims_only_selected_product_and_zip_without_listing_gate(client):
    first = create_ready_product(client)
    selected = create_ready_product(client, source_id='987654321')
    enable(client)
    enqueue(client, first)  # Older broad jobs must not escape the trial scope.
    policy = configure_trial(client, selected)
    assert enqueue(client, selected)['manual_ready'] is True
    job = claim(client)
    assert job['supplier_product_id'] == policy['trial']['supplier_product_id']
    assert job['postal_code'] == '60601'
    assert claim(client, 'isolated-2') is None
    assert complete(client, job).status_code == 200
    assert claim(client) is None
    assert client.get('/delivery-quotes/policy').json()['enabled'] is False
    assert len(client.get(f"/delivery-quotes/products/{selected['id']}").json()['quotes']) == 1
    # Removing trial leaves broad checking off; enabling broad checking later resumes old jobs.
    assert client.put('/delivery-quotes/policy', json={'enabled': False, 'postal_codes': ['33101']}).status_code == 200
    assert claim(client) is None
    enable(client)
    assert claim(client)['supplier_product_id'] != policy['trial']['supplier_product_id']


def test_trial_runs_without_listing_and_revocation_cannot_resurrect_lease(client):
    product = create_ready_product(client)
    policy = configure_trial(client, product)
    job = claim(client)
    assert job is not None
    assert client.put('/delivery-quotes/policy', json={'enabled': False, 'postal_codes': ['33101']}).status_code == 200
    assert client.put('/delivery-quotes/policy', json=policy).status_code == 200
    lease = {'worker_id': 'isolated-1', 'lease_token': job['lease_token']}
    assert client.post(f"/delivery-quotes/jobs/{job['id']}/heartbeat", json=lease).status_code == 409
    assert complete(client, job).status_code == 409
    assert client.post(f"/delivery-quotes/jobs/{job['id']}/failed", json={**lease, 'message': 'old', 'retryable': True}).status_code == 409
    assert claim(client) is None
    assert client.get('/delivery-quotes/jobs').json()[0]['status'] == 'needs_review'


def test_switch_trial_revokes_old_scope_and_leases_only_new_scope(client):
    first = create_ready_product(client)
    second = create_ready_product(client, source_id='987654321')
    configure_trial(client, first)
    old = claim(client)
    configure_trial(client, second, '75201')
    assert complete(client, old).status_code == 409
    new = claim(client)
    assert new['source_url'].endswith('987654321') and new['postal_code'] == '75201'
    assert complete(client, new).status_code == 200
    assert client.get(f"/delivery-quotes/products/{first['id']}").json()['quotes'] == []


def test_trial_rejects_invalid_scope_without_changing_policy_or_lease(client):
    product = create_ready_product(client)
    policy = configure_trial(client, product)
    job = claim(client)
    invalid_policies = [
        {**policy, 'enabled': True},
        {**policy, 'trial': {'supplier_product_id': 999999, 'postal_code': '60601'}},
        {**policy, 'trial': {'supplier_product_id': True, 'postal_code': '60601'}},
        {**policy, 'trial': {**policy['trial'], 'postal_code': 'invalid'}},
    ]
    for invalid in invalid_policies:
        assert client.put('/delivery-quotes/policy', json=invalid).status_code == 422
        assert client.get('/delivery-quotes/policy').json() == policy
    assert claim(client)['lease_token'] == job['lease_token']
    assert complete(client, job).status_code == 200


def test_trial_selects_explicit_supplier_even_when_first_supplier_is_not_home_depot(client):
    product = create_ready_product(client)
    supplier_ids = []
    def add_supplier(db):
        first = db.scalar(select(SupplierProduct).where(SupplierProduct.product_id == product['id']))
        first.source_url = 'https://www.amazon.com/dp/B012345678'
        selected = SupplierProduct(product_id=product['id'], source_url='https://www.homedepot.com/p/Test/987654321')
        db.add(selected)
        db.flush()
        supplier_ids.append(selected.id)
    mutate(client, add_supplier)
    policy = {'enabled': False, 'postal_codes': ['33101'],
              'trial': {'supplier_product_id': supplier_ids[0], 'postal_code': '60601'}}
    assert client.put('/delivery-quotes/policy', json=policy).status_code == 200
    job = claim(client)
    assert job['supplier_product_id'] == supplier_ids[0]
    assert complete(client, job).status_code == 200


def test_changing_only_trial_zip_revokes_old_lease(client):
    product = create_ready_product(client)
    configure_trial(client, product)
    old = claim(client)
    configure_trial(client, product, '75201')
    assert complete(client, old).status_code == 409
    job = claim(client)
    assert job['postal_code'] == '75201'
    assert complete(client, job).status_code == 200

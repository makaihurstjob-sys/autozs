from datetime import datetime, timedelta

from test_delivery_checks import claim, enable, enqueue, mutate
from test_listing_jobs import create_ready_product
from app.models.domain import DeliveryCheckJob


def held_for_review(client, worker='isolated-1'):
    product = create_ready_product(client)
    enable(client, ['33101'])
    enqueue(client, product)
    job = claim(client, worker)
    response = client.post(f"/delivery-quotes/jobs/{job['id']}/failed", json={
        'worker_id': worker, 'lease_token': job['lease_token'],
        'message': 'Transient supplier page error: Home Depot requested a refresh'})
    assert response.json()['status'] == 'needs_review'
    return job


def cart_cleared(client, job_id, worker='isolated-1'):
    return client.post(f'/delivery-quotes/jobs/{job_id}/cart-cleared', json={'worker_id': worker})


def make_due(client, job_id):
    def advance_retry(db):
        db.get(DeliveryCheckJob, job_id).retry_at = datetime.utcnow() - timedelta(seconds=1)
    mutate(client, advance_retry)


def test_cleared_cart_retries_held_check_within_attempt_budget(client):
    job = held_for_review(client)
    response = cart_cleared(client, job['id'])
    assert response.status_code == 200
    retried = response.json()
    assert (retried['status'], retried['attempts']) == ('queued', 1)
    assert retried['message'] == 'Retrying after the worker cleared its cart: Transient supplier page error: Home Depot requested a refresh'
    assert claim(client) is None
    make_due(client, job['id'])
    again = claim(client)
    assert (again['id'], again['attempts']) == (job['id'], 2)


def test_cleared_cart_never_retries_past_the_attempt_budget(client):
    job = held_for_review(client)
    for attempt in (2, 3):
        assert cart_cleared(client, job['id']).json()['status'] == 'queued'
        make_due(client, job['id'])
        job = claim(client)
        assert job['attempts'] == attempt
        client.post(f"/delivery-quotes/jobs/{job['id']}/failed", json={
            'worker_id': 'isolated-1', 'lease_token': job['lease_token'], 'message': 'Cart page failed again'})
    exhausted = cart_cleared(client, job['id'])
    assert exhausted.status_code == 200
    assert (exhausted.json()['status'], exhausted.json()['message']) == ('needs_review', 'Cart page failed again')
    assert claim(client) is None


def test_only_the_worker_holding_a_reviewed_check_can_release_it(client):
    job = held_for_review(client)
    assert cart_cleared(client, job['id'], worker='isolated-2').status_code == 409
    assert cart_cleared(client, 999999).status_code == 404
    assert cart_cleared(client, job['id']).status_code == 200
    assert cart_cleared(client, job['id']).status_code == 409
    make_due(client, job['id'])
    running = claim(client)
    assert cart_cleared(client, running['id']).status_code == 409
    assert client.get('/delivery-quotes/jobs').json()[0]['status'] == 'running'

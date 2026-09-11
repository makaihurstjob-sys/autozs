from test_listing_jobs import create_ready_product


def quote(client, zip_code="33101", charge=35, quantity=1):
    return client.post('/delivery-quotes/cart', json={
        'source_url': 'https://www.homedepot.com/p/Queue-Ready/123456789',
        'postal_code': zip_code, 'quantity': quantity, 'delivery_charge': charge,
    })


def test_paid_quote_blocks_new_and_already_queued_listing(client):
    product = create_ready_product(client)
    job = client.post('/listing-jobs', json={'product_ids': [product['id']]}).json()[0]
    assert quote(client).status_code == 200
    blocked = client.post('/listing-jobs', json={'product_ids': [product['id']]})
    assert blocked.status_code == 409
    assert '$35.00' in blocked.json()['detail']
    result = client.post(f"/listing-jobs/{job['id']}/run").json()['job']
    assert result['status'] == 'needs_review'
    assert '$35.00' in result['message'] and '33101' in result['message']


def test_quote_upsert_and_other_zip_cannot_clear_risk(client):
    product = create_ready_product(client)
    assert quote(client).status_code == 200
    assert quote(client).status_code == 200
    assert quote(client, '10001', 0).status_code == 200
    url = f"/delivery-quotes/products/{product['id']}"
    result = client.get(url).json()
    assert len(result['quotes']) == 2
    assert result['blocking_reason']
    assert result['nationwide_free_shipping_verified'] is False
    assert quote(client, charge=0, quantity=2).status_code == 200
    assert client.get(url).json()['blocking_reason']
    assert quote(client, charge=0).status_code == 200
    assert client.get(url).json()['blocking_reason'] is None


def test_invalid_observations_rejected(client):
    create_ready_product(client)
    for kwargs in ({'zip_code': '3310'}, {'charge': -1}, {'quantity': 0}, {'quantity': 1.5}):
        assert quote(client, **kwargs).status_code == 422
    assert client.post('/delivery-quotes/cart', json={
        'source_url': 'https://www.homedepot.com.evil.test/p/Other/123456789',
        'postal_code': '33101', 'quantity': 1, 'delivery_charge': 0,
    }).status_code == 422


def test_stale_paid_quote_stays_blocking(client):
    from datetime import datetime, timedelta
    from app.core.database import get_db
    from app.main import app
    from app.models.domain import SupplierDeliveryQuote
    from sqlalchemy import select
    product = create_ready_product(client)
    quote(client)
    session = app.dependency_overrides[get_db]()
    db = next(session)
    db.scalar(select(SupplierDeliveryQuote)).observed_at = datetime.utcnow() - timedelta(days=30)
    db.commit()
    session.close()
    result = client.get(f"/delivery-quotes/products/{product['id']}").json()
    assert result['quotes'][0]['stale'] is True
    assert result['blocking_reason']

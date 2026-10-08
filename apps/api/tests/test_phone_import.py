from app.models.domain import ListingJob, Product, SupplierProduct
from sqlalchemy import select

URL = "https://www.homedepot.com/p/Test-Garden-Nozzle/123456789"


def test_phone_import_duplicate_and_capture_remain_draft(client):
    first = client.post('/products/phone-import', json={'source_url': URL + '?tracking=phone'})
    assert first.status_code == 200
    item = first.json()
    assert item['created'] and item['status'] == 'draft'
    queue = client.get('/products/capture-queue').json()
    assert any(row['product_id'] == item['product_id'] for row in queue['items'])
    repeated = client.post('/products/phone-import', json={'source_url': URL}).json()
    assert not repeated['created'] and repeated['product_id'] == item['product_id']
    captured = client.post('/products/import-captured', json={
        'source_url': URL + '?ea_auto_import=1', 'title': 'Garden Nozzle',
        'source_price': 19.99, 'source_shipping': 0, 'source_in_stock': True,
        'image_urls': 'https://images.test/nozzle.jpg', 'description': 'A garden nozzle.',
    })
    assert captured.status_code == 200
    assert captured.json()['id'] == item['product_id']
    assert captured.json()['status'] == 'draft'
    assert captured.json()['supplier_products'][0]['last_price'] == 19.99
    assert client.get('/listing-jobs').json() == []


def test_phone_import_existing_product_is_untouched(client):
    client.post('/products/phone-import', json={'source_url': URL})
    from app.core.database import get_db
    db = next(client.app.dependency_overrides[get_db]())
    product = db.scalar(select(Product))
    product.status = 'paused'
    supplier = db.scalar(select(SupplierProduct))
    supplier.last_price = 23.45
    db.commit()
    response = client.post('/products/phone-import', json={'source_url': URL}).json()
    assert response['status'] == 'paused' and not response['created']
    db.expire_all()
    assert db.get(Product, product.id).status == 'paused'
    assert db.scalar(select(SupplierProduct)).last_price == 23.45
    assert db.scalars(select(ListingJob)).all() == []
    db.close()


def test_phone_import_rejects_other_hosts_and_short_links(client):
    for url in ['http://www.homedepot.com/p/Test/123456789', 'https://evil.example/p/Test/123456789',
                'https://www.homedepot.com.evil.example/p/Test/123456789',
                'https://www.homedepot.com/search?q=nozzle', 'https://homedepot.sjv.io/abc',
                'https://user@www.homedepot.com/p/Test/123456789', 'https://www.homedepot.com:444/p/Test/123456789']:
        assert client.post('/products/phone-import', json={'source_url': url}).status_code == 400
    assert client.get('/products').json() == []

import pytest
from app.main import app
from app.core.database import get_db
from app.models.domain import Order, SupplierOrder, AppSetting
from app.services.supplier_receipts import parse_receipt

TEXT = 'Subtotal: $4.88 Delivery: FREE Sales Tax: $0.40 Total: $5.28'


def test_receipt_requires_balanced_complete_breakdown():
    assert parse_receipt(TEXT)['total'] == 5.28
    for invalid in [TEXT.replace('$5.28', '$5.29'), TEXT + ' Refund $1.00', TEXT.replace('FREE', 'Unknown')]:
        with pytest.raises(ValueError):
            parse_receipt(invalid)


def test_receipt_capture_is_idempotent_and_mismatch_never_changes_payment(client):
    db = next(app.dependency_overrides[get_db]())
    order = Order(ebay_order_id='sale-receipt', account_id='real', status='shipped')
    db.add(order)
    db.flush()
    supplier = SupplierOrder(order_id=order.id, supplier='home_depot', status='shipped', external_order_id='WK37553521', item_subtotal=4.88, sales_tax=.40, shipping_cost=0, total=5.28, card_amount=5.28)
    db.add(supplier)
    db.commit()
    candidate = client.post('/finance/supplier-receipts/next').json()
    assert candidate['supplier_order_id'] == supplier.id
    assert client.post('/finance/supplier-receipts/next').json() is None
    payload = {'source_url':candidate['url'], 'external_order_id':supplier.external_order_id, 'financial_text':TEXT}
    endpoint = f'/finance/supplier-receipts/{supplier.id}'
    for _ in range(2):
        response = client.post(endpoint, json=payload)
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'verified'
    assert db.query(AppSetting).filter(AppSetting.key.like('supplier_receipt:%')).count() == 1
    payload['financial_text'] = TEXT.replace('$4.88', '$5.88').replace('$5.28', '$6.28')
    assert client.post(endpoint, json=payload).json()['status'] == 'needs_review'
    db.refresh(supplier)
    assert supplier.total == supplier.card_amount == 5.28
    row = client.get('/finance/overview').json()['profitability']['orders'][0]
    assert row['contribution'] is None
    assert any('supplier receipt' in reason for reason in row['missing'])
    payload['source_url'] = candidate['url'].replace('WK37553521', 'WK00000000')
    assert client.post(endpoint, json=payload).status_code == 422
    assert client.post('/finance/supplier-receipts/99999',json=payload).status_code == 404
    db.close()

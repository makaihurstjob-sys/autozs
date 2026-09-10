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


def test_single_card_charge_corrects_costs_and_keeps_audit(client):
    import json
    db = next(app.dependency_overrides[get_db]())
    sale = Order(ebay_order_id='charge-sale', account_id='real', status='shipped')
    db.add(sale)
    db.flush()
    supplier = SupplierOrder(order_id=sale.id, status='shipped', external_order_id='WK35437792', total=3.36, card_amount=3.36)
    db.add(supplier)
    db.commit()
    charge = 'Charge History CHARGE August 19, 2026 | MA - 1113 $2.79 Subtotal $2.58 Delivery FREE Pickup FREE ProXtra Savings FREE Sales Tax (8.14%) $0.21 Refund Total $0.00 Original Total $2.79 Adjusted Total $2.79'
    payload = {'source_url':'https://www.homedepot.com/myaccount/order-details?orderNumber=WK35437792', 'external_order_id':'WK35437792', 'financial_text':'Subtotal: $2.58 Delivery: FREE Sales Tax: $0.21 Total: $2.79', 'charge_history_text':charge}
    endpoint = f'/finance/supplier-receipts/{supplier.id}'
    for _ in range(2):
        result = client.post(endpoint,json=payload)
        assert result.status_code == 200, result.text
        assert result.json()['charge_verified']
        assert result.json()['payment_corrected']
    db.refresh(supplier)
    assert supplier.total == supplier.card_amount == 2.79
    evidence = db.query(AppSetting).filter(AppSetting.key.like('supplier_receipt:%')).one()
    assert json.loads(evidence.value)['previous_card_amount'] == 3.36
    for bad in [charge.replace('Refund Total $0.00','Refund Total $0.50'), charge + ' CHARGE $1.00', charge.replace('MA -','GIFT -')]:
        payload['charge_history_text'] = bad
        assert client.post(endpoint,json=payload).status_code == 422
    db.refresh(supplier)
    assert supplier.card_amount == 2.79
    db.close()

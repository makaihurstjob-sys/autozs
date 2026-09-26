from datetime import datetime, timedelta, timezone
import pytest
from app.main import app
from app.core.database import get_db
from app.models.domain import SupplierOrder, EbayCheckoutVerification
from test_fulfillment import _prepare_order
from ebay_verification_helpers import verify_queued


def setup_order(client):
    row = _prepare_order(client).json()
    assert client.post(f"/supplier-orders/{row['id']}/approve").status_code == 200
    identity = client.get("/supplier-orders/ebay-verification-next").json()
    return row, {"ebay_order_id": identity["ebay_order_id"], "account_key": identity["account_key"],
                 "source_url": "https://www.ebay.com/mesh/ord/details?mode=SH&orderid=" + identity["ebay_order_id"],
                 "status": "eligible", "observed_at": datetime.now(timezone.utc).isoformat(),
                 "evidence": "Paid. Awaiting shipment. Ship by Monday."}


def test_missing_evidence_leaves_queued_without_attempt(client):
    row, payload = setup_order(client)
    assert client.post("/supplier-orders/next").json() is None
    current = client.get(f"/supplier-orders/{row['id']}").json()
    assert current['status'] == 'queued' and current['attempts'] == 0
    assert verify_queued(client).status_code == 200
    assert client.post("/supplier-orders/next").json()['id'] == row['id']
    assert client.post("/supplier-orders/next").json() is None


@pytest.mark.parametrize('field,value', [('account_key','wrong'), ('ebay_order_id','wrong'),
    ('source_url','https://evil.example/mesh/ord/details?orderid=wrong'),
    ('observed_at',(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()),
    ('observed_at',(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()), ('evidence',' ')])
def test_reject_invalid_identity_or_time(client, field, value):
    row, payload = setup_order(client)
    payload[field] = value
    assert client.post(f"/supplier-orders/{row['id']}/ebay-verification",json=payload).status_code == 422
    assert client.post("/supplier-orders/next").json() is None


@pytest.mark.parametrize('status',['cancelled','refunded','fulfilled','unknown'])
def test_negative_observation_revokes_checkout_without_supplier_refund_claim(client,status):
    row,payload=setup_order(client)
    assert verify_queued(client).status_code == 200
    claimed=client.post('/supplier-orders/next').json()
    payload['status']=status
    assert client.post(f"/supplier-orders/{row['id']}/ebay-verification",json=payload).status_code==200
    current=client.get(f"/supplier-orders/{row['id']}").json()
    assert current['status']=='needs_review'
    assert status in current['failure_reason']
    assert client.post(f"/supplier-orders/{row['id']}/checkout-credential",headers={
        'X-AutoZS-Checkout-Token':claimed['checkout_token']}).status_code==403
    assert client.post('/supplier-orders/next').json() is None


@pytest.mark.parametrize('mutation',['stale','lease','purchased','account','cancelled'])
def test_credentials_recheck_freshness_identity_and_purchase(client,mutation):
    row,payload=setup_order(client)
    assert verify_queued(client).status_code == 200
    claimed=client.post('/supplier-orders/next').json()
    db=next(app.dependency_overrides[get_db]())
    supplier=db.get(SupplierOrder,row['id'])
    if mutation=='stale': db.query(EbayCheckoutVerification).one().observed_at=datetime.utcnow()-timedelta(minutes=3)
    if mutation=='lease': supplier.lease_expires_at=datetime.utcnow()-timedelta(seconds=1)
    if mutation=='purchased': supplier.external_order_id='ALREADY-BOUGHT'
    if mutation=='account': supplier.order.account_id='OTHER'
    if mutation=='cancelled': supplier.order.status='cancelled'
    db.commit()
    response=client.post(f"/supplier-orders/{row['id']}/checkout-credential",headers={
        'X-AutoZS-Checkout-Token':claimed['checkout_token']})
    assert response.status_code in {403,422}
    if mutation in {'purchased','cancelled'}:
        assert client.get(f"/supplier-orders/{row['id']}/ebay-verification-context").status_code==422
    db.close()


def test_terminal_evidence_cannot_be_reopened_by_reapproval(client):
    row,payload=setup_order(client)
    payload['status']='cancelled'
    assert client.post(f"/supplier-orders/{row['id']}/ebay-verification",json=payload).status_code==200
    assert client.post(f"/supplier-orders/{row['id']}/approve").status_code==200
    payload['status']='unknown'
    assert client.post(f"/supplier-orders/{row['id']}/ebay-verification",json=payload).status_code==200
    assert client.post(f"/supplier-orders/{row['id']}/approve").status_code==200
    payload['status']='eligible'
    assert client.post(f"/supplier-orders/{row['id']}/ebay-verification",json=payload).status_code==422
    assert client.post('/supplier-orders/next').json() is None


def test_expired_evidence_cannot_claim_checkout(client):
    row,payload=setup_order(client)
    assert verify_queued(client).status_code==200
    db=next(app.dependency_overrides[get_db]())
    db.query(EbayCheckoutVerification).one().observed_at=datetime.utcnow()-timedelta(minutes=3)
    db.commit()
    assert client.post('/supplier-orders/next').json() is None
    assert client.get(f"/supplier-orders/{row['id']}").json()['status']=='queued'
    db.close()


def test_unknown_requires_reapproval_and_new_evidence(client):
    row,payload=setup_order(client)
    payload['status']='unknown'
    assert client.post(f"/supplier-orders/{row['id']}/ebay-verification",json=payload).status_code==200
    payload['status']='eligible'
    assert client.post(f"/supplier-orders/{row['id']}/ebay-verification",json=payload).status_code==422
    assert client.post(f"/supplier-orders/{row['id']}/approve").status_code==200
    assert client.post('/supplier-orders/next').json() is None
    assert verify_queued(client).status_code==200
    assert client.post('/supplier-orders/next').json()['id']==row['id']

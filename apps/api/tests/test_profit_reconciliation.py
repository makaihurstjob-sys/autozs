from datetime import datetime
import pytest
from app.main import app
from app.core.database import get_db
from app.models.domain import Order, OrderItem, AppSetting
from app.services.profit_reconciliation import parse_financial_text

TEXT = "What your buyer paid Subtotal $9.53 Shipping $0.00 Sales tax* $0.69 Order total** $10.22 What you earned Order total $10.22 eBay collected from buyer Sales tax -$0.69 Selling costs Transaction fees -$1.79 Order earnings $7.74"


def setup_order(client):
    db = next(app.dependency_overrides[get_db]())
    order = Order(ebay_order_id="08-15143-56000", account_id="real", status="shipped", total=10.22)
    db.add(order); db.flush()
    db.add(OrderItem(order_id=order.id,title="Nozzle",quantity=1,sale_price=9.53))
    db.commit()
    return db,order


def test_exact_financial_reconciliation():
    assert parse_financial_text(TEXT)["fees"] == 1.79
    for bad in [TEXT.replace("$7.74", "$7.75"), TEXT.replace("Transaction fees", "Refund"), TEXT + " Other cost $1.00", TEXT.replace("$0.69", "$0.68", 1)]:
        with pytest.raises(ValueError): parse_financial_text(bad)


def test_marketplace_collected_delivery_fee_is_not_seller_cost():
    text = TEXT.replace("Sales tax* $0.69", "Sales tax* $0.69 Retail delivery fees* $0.31").replace("$10.22", "$10.53").replace("Sales tax -$0.69", "Sales tax -$0.69 Retail delivery fees -$0.31")
    assert parse_financial_text(text)["fees"] == 1.79
    assert parse_financial_text(text)["marketplace_collected_retail_delivery_fee"] == .31
    with pytest.raises(ValueError):
        parse_financial_text(text.replace("fees -$0.31", "fees -$0.30"))


def test_automatic_capture_idempotent_and_cooldown(client):
    db,order = setup_order(client)
    candidate = client.post("/finance/reconciliation/next?account_key=real").json()
    assert candidate["order_id"] == order.id
    assert client.post("/finance/reconciliation/next?account_key=real").json() is None
    payload = {"source_url":candidate["url"], "account_key":"real", "ebay_order_id":order.ebay_order_id,"financial_text":TEXT,"paid_date":"Sep 8, 2026"}
    for _ in range(2):
        response=client.post(f"/finance/reconciliation/{order.id}",json=payload)
        assert response.status_code == 200, response.text
    db.refresh(order)
    assert order.ebay_fee_amount == 1.79
    assert order.buyer_shipping_revenue == 0
    assert order.paid_at == datetime(2026,9,8)
    assert db.query(AppSetting).filter(AppSetting.key.like("profit_evidence:%")).count() == 1
    assert client.get("/finance/overview").json()["profitability"]["orders"][0]["reconciliation"]["status"] == "verified"
    db.close()


def test_wrong_order_and_unbalanced_fees_never_overwrite(client):
    db,order=setup_order(client)
    payload={"source_url":"https://www.ebay.com/mesh/ord/details?orderid=WRONG","account_key":"real", "ebay_order_id":order.ebay_order_id,"financial_text":TEXT}
    assert client.post(f"/finance/reconciliation/{order.id}",json=payload).status_code == 422
    db.refresh(order)
    assert order.ebay_fee_amount is None
    row=client.get("/finance/overview").json()["profitability"]["orders"][0]
    assert row["contribution"] is None
    assert row["reconciliation"]["status"] == "needs_review"
    db.close()

from ebay_verification_helpers import verify_queued
import base64
from datetime import datetime, timezone


def test_finance_overview_tracks_accounts_subscriptions_and_expenses(client) -> None:
    bank = client.post(
        "/finance/accounts",
        json={
            "provider": "plaid_bridge",
            "external_id": "bank-001",
            "account_type": "bank",
            "name": "Business checking",
            "mask": "4321",
            "current_balance": 1250.0,
            "available_balance": 1200.0,
        },
    )
    assert bank.status_code == 200

    ebay = client.post(
        "/finance/accounts",
        json={
            "provider": "ebay_chrome",
            "external_id": "a.m.anim-59",
            "account_type": "ebay",
            "name": "a.m.anim-59 eBay funds",
            "current_balance": 125.0,
            "available_balance": 75.0,
            "held_balance": 50.0,
        },
    )
    assert ebay.status_code == 200

    subscription = client.post(
        "/finance/subscriptions",
        json={"name": "AutoZS hosting", "amount": 20.0, "cadence": "monthly"},
    )
    assert subscription.status_code == 200

    imported = client.post(
        "/finance/entries/import",
        json=[
            {
                "provider": "plaid_bridge",
                "external_id": "transaction-001",
                "financial_account_id": bank.json()["id"],
                "entry_type": "expense",
                "category": "software",
                "amount": -20.0,
                "description": "AutoZS hosting",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    ).json()
    assert imported["imported"] == 1

    overview = client.get("/finance/overview").json()
    assert overview["bank_balance"] == 1250.0
    assert overview["ebay_available"] == 75.0
    assert overview["ebay_held"] == 50.0
    assert overview["operating_expenses"] == 20.0
    assert overview["subscriptions"][0]["name"] == "AutoZS hosting"
    assert overview["periods"][0]["period"] == "All time"
    assert overview["profit_verified"] is False
    assert overview["available_business_profit"] == 0.0


def test_finance_profit_stays_unverified_when_fulfilled_order_has_no_supplier_cost_or_fees(client) -> None:
    queued = client.post("/orders/sync?account_key=a.m.anim-59").json()
    claimed = client.post("/orders/sync/next?account_key=a.m.anim-59").json()
    report = (
        "Order Number,Buyer Username,Ship To Name,Ship To Address 1,Ship To Address 2,Ship To City,Ship To State,Ship To Zip,Ship To Country,Item Number,Item Title,Custom Label,Quantity,"
        "Sold For,Shipping And Handling,Total Price,Paid On Date,Ship By Date,Shipped On Date,Shipping Service,Tracking Number\n"
        "22-11111-22222,buyer,Test Buyer,1 Main St,,Denver,CO,80202,United States,800123456789,Test item,,1,"
        "$10.00,$0.00,$10.80,Aug-20-26,Aug-22-26,Aug-21-26,USPS,9400000000000000000000\n"
    ).encode()
    order = client.post("/orders/import-file", json={
        "account_key": "a.m.anim-59",
        "run_id": claimed["id"],
        "filename": "finance-order.csv",
        "report_base64": base64.b64encode(report).decode(),
    })
    assert order.status_code == 200, order.text
    overview = client.get("/finance/overview").json()
    assert overview["gross_merchandise_revenue"] == 10.0
    assert overview["realized_revenue"] == 10.0
    assert overview["profit_verified"] is False
    assert overview["verified_profit"] is None
    assert overview["available_business_profit"] == 0.0
    assert overview["unverified_order_count"] == 1
    assert any("supplier" in issue.lower() for issue in overview["profit_data_issues"])
    assert any("fee" in issue.lower() for issue in overview["profit_data_issues"])


def test_finance_exposes_liquidity_bounded_profit_only_after_cost_and_fee_evidence(client) -> None:
    client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Finance-Verified/123456",
            "title": "Finance Verified Product",
            "source_price": 20.0,
            "source_shipping": 0.0,
        },
    )
    order = client.post("/orders/sync-sandbox").json()
    prepared = client.post(f"/orders/{order['id']}/supplier-orders/prepare", json={
        "recipient_name": "Test Buyer",
        "address_line1": "1 Main Street",
        "city": "Denver",
        "state": "CO",
        "postal_code": "80202",
    }).json()
    approved = client.post(f"/supplier-orders/{prepared['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert verify_queued(client).status_code == 200
    claimed = client.post("/supplier-orders/next")
    assert claimed.status_code == 200, claimed.text
    placed = client.patch(f"/supplier-orders/{prepared['id']}", json={
        "status": "placed",
        "external_order_id": "HD-VERIFIED-1",
        "item_subtotal": 20.0,
        "sales_tax": 0.0,
        "shipping_cost": 0.0,
        "card_amount": 20.0,
        "total": 20.0,
    })
    assert placed.status_code == 200, placed.text
    # Available funds come from a verified Robinhood balance specifically --
    # any other provider (the old z_finance/plaid-style accounts) no longer
    # counts toward liquidity, per the corrected accounting rules.
    client.post("/finance/accounts", json={
        "provider": "robinhood",
        "external_id": "robinhood-verified",
        "account_type": "bank",
        "name": "Robinhood available funds",
        "current_balance": 100.0,
        "available_balance": 100.0,
    }).json()
    fee_response = client.post(f"/orders/{order['id']}/ebay-fee", json={
        "fee_amount": 5.0,
        "evidence_ref": "eBay Seller Hub order 22-00000-00000",
    })
    assert fee_response.status_code == 200, fee_response.text
    overview = client.get("/finance/overview").json()
    assert overview["profit_verified"] is True
    assert overview["verified_profit"] is not None
    assert overview["available_business_profit"] == max(0.0, overview["verified_profit"])
    assert overview["profit_data_issues"] == []


def test_ebay_fee_requires_a_real_evidence_reference(client) -> None:
    client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Fee-Evidence/999999",
            "title": "Fee Evidence Product",
            "source_price": 10.0,
            "source_shipping": 0.0,
        },
    )
    order = client.post("/orders/sync-sandbox").json()

    rejected = client.post(f"/orders/{order['id']}/ebay-fee", json={"fee_amount": 2.0, "evidence_ref": "   "})
    assert rejected.status_code == 422

    missing_order = client.post(f"/orders/999999/ebay-fee", json={"fee_amount": 2.0, "evidence_ref": "ref"})
    assert missing_order.status_code == 404


def test_finance_liquidity_ignores_non_robinhood_accounts(client) -> None:
    # A z_finance-style (or any other non-Robinhood) account balance must never
    # count toward available_business_profit -- that's the whole point of the
    # corrected accounting rules.
    client.post("/finance/accounts", json={
        "provider": "z_finance",
        "external_id": "old-bank-1",
        "account_type": "bank",
        "name": "Old operating account",
        "current_balance": 5000.0,
        "available_balance": 5000.0,
    })
    overview = client.get("/finance/overview").json()
    assert any("Robinhood" in issue for issue in overview["profit_data_issues"])
    assert overview["available_business_profit"] == 0.0


def test_profitability_uses_receipts_not_tax_balances_or_missing_fees(client):
    from app.main import app
    from app.core.database import get_db
    from app.models.domain import Order, OrderItem, SupplierOrder
    db = next(app.dependency_overrides[get_db]())
    order = Order(ebay_order_id="profit-real", account_id="real", status="shipped", total=24.60,
                  buyer_shipping_revenue=3, paid_at=datetime(2026, 9, 2))
    db.add(order); db.flush()
    db.add(OrderItem(order_id=order.id, title="Test", quantity=2, sale_price=10))
    db.add(SupplierOrder(order_id=order.id, status="shipped", external_order_id="receipt-1", total=12, card_amount=12))
    db.commit()
    report = client.get("/finance/overview").json()["profitability"]
    assert report["orders"][0]["revenue"] == 23
    assert report["orders"][0]["contribution"] is None
    assert report["months"][0]["recorded_net"] is None
    response = client.post(f"/orders/{order.id}/ebay-fee", json={"fee_amount":3,"evidence_ref":"transaction-1"})
    assert response.status_code == 200
    client.post("/finance/subscriptions", json={"name":"Annual tool", "amount":120, "cadence":"annual"})
    client.post("/finance/entries/import", json=[{"provider":"test", "external_id":"expense-1", "entry_type":"expense", "category":"software", "amount":-2, "occurred_at":"2026-09-04T12:00:00"}, {"provider":"test", "external_id":"refund-1", "entry_type":"refund", "category":"refund", "amount":-1, "occurred_at":"2026-09-04T12:00:00"}])
    report = client.get("/finance/overview").json()["profitability"]
    assert report["orders"][0]["contribution"] == 8
    assert report["months"][0]["recorded_net"] == 5
    assert report["monthly_subscription_run_rate"] == 10
    # A scheduled subscription is not double deducted from actual expenses.
    assert report["complete_orders"] == 1
    db.close()


def test_profitability_rejects_unbalanced_supplier_payments_and_unknown_shipping(client):
    from app.main import app
    from app.core.database import get_db
    from app.models.domain import Order, OrderItem, SupplierOrder
    db = next(app.dependency_overrides[get_db]())
    order = Order(ebay_order_id="profit-missing", account_id="real", status="shipped", total=20)
    db.add(order); db.flush()
    db.add(OrderItem(order_id=order.id, title="Test", quantity=1, sale_price=20))
    db.add(SupplierOrder(order_id=order.id, status="shipped", external_order_id="receipt", total=12, card_amount=0))
    db.commit()
    row = client.get("/finance/overview").json()["profitability"]["orders"][0]
    assert row["supplier_cost"] is None
    assert row["buyer_shipping"] is None
    assert row["contribution"] is None
    assert row["month"] == "Unknown payment month"
    db.close()

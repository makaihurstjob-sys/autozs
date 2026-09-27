from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_purchase_budget import engine

from app.core.database import Base
from app.models.domain import (AppSetting, Order, OrderItem, SupplierOrder, SupplierOrderItem,
                               EbayCheckoutVerification, PurchaseReservation)
from app.services.purchase_submission import FinalCheckout, authorize_submission
from app.services.fulfillment import update_supplier_order


@pytest.fixture
def ready(engine):
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as db, db.begin():
        order = db.get(Order, 1)
        order.account_id = "test-seller"
        order.ebay_fee_amount = 1
        order.ebay_fee_evidence_ref = "verified-test"
        order.ebay_fee_recorded_at = now
        order.buyer_shipping_revenue = 0
        row = db.get(SupplierOrder, 1)
        row.status = "placing"
        row.checkout_token = "test-token"
        row.approved_total = 10
        row.approved_at = now - timedelta(minutes=1)
        row.lease_expires_at = now + timedelta(minutes=5)
        db.add(OrderItem(order_id=1, title="Test", quantity=1, sale_price=12))
        db.add(SupplierOrderItem(supplier_order_id=1, title="Test", quantity=1, unit_price=8))
        db.add(EbayCheckoutVerification(supplier_order_id=1, ebay_order_id="test-1",
            account_key="test-seller", source_url="https://www.ebay.com/mesh/ord/details?orderid=test-1",
            observed_at=now, verified_at=now, status="eligible", evidence="Paid; awaiting shipment"))
        for key, value in {"purchase_automation_enabled": "true",
            "owner_place_order:1": row.approved_at.isoformat(),
            "profit_reconciliation:1": json.dumps({"status": "verified"}),
            "purchase_other_costs:1": json.dumps({"amount": "0", "evidence": "test all-cost review"})}.items():
            db.add(AppSetting(key=key, value=value))
    return engine


def quote(**changes):
    values = dict(item_subtotal="8", shipping="1", tax="1", total="10",
                  source_url="https://www.homedepot.com/checkout", observed_at=datetime.now(timezone.utc))
    values.update(changes)
    return FinalCheckout(**values)


def test_final_permission_is_committed_once_and_confirmation_reconciles(ready):
    with Session(ready) as db:
        result = authorize_submission(db, 1, "test-token", quote())
        assert result["authorized"] and result["total_cents"] == 1000
    with Session(ready) as db:
        assert db.scalar(select(PurchaseReservation)).status == "submitting"
        with pytest.raises(ValueError, match="already reserved"):
            authorize_submission(db, 1, "test-token", quote())
        db.rollback()
        update_supplier_order(db, db.get(SupplierOrder, 1),
                              {"status": "placed", "external_order_id": "HD-123", "total": 10})
        assert db.scalar(select(PurchaseReservation)).status == "purchased"


@pytest.mark.parametrize("field,value", [("status", "cancelled"), ("checkout_token", "wrong"),
    ("lease_expires_at", datetime(2020, 1, 1))])
def test_invalid_lease_or_state_cannot_reserve(ready, field, value):
    with Session(ready) as db, db.begin():
        setattr(db.get(SupplierOrder, 1), field, value)
    with Session(ready) as db, pytest.raises(ValueError, match="lease"):
        authorize_submission(db, 1, "test-token", quote())


@pytest.mark.parametrize("key", ["purchase_automation_enabled", "purchase_other_costs:1", "profit_reconciliation:1"])
def test_missing_policy_or_evidence_blocks_without_reservation(ready, key):
    with Session(ready) as db, db.begin():
        db.delete(db.scalar(select(AppSetting).where(AppSetting.key == key)))
    with Session(ready) as db:
        with pytest.raises(ValueError):
            authorize_submission(db, 1, "test-token", quote())
        db.rollback()
        assert db.scalar(select(PurchaseReservation)) is None


def test_stale_quote_and_stale_ebay_observation_block(ready):
    with Session(ready) as db:
        with pytest.raises(ValueError, match="stale"):
            authorize_submission(db, 1, "test-token", quote(observed_at=datetime(2020, 1, 1, tzinfo=timezone.utc)))
        db.rollback()
        db.scalar(select(EbayCheckoutVerification)).observed_at = datetime(2020, 1, 1)
        db.commit()
        with pytest.raises(ValueError, match="Fresh eligible"):
            authorize_submission(db, 1, "test-token", quote())


def test_failure_keeps_budget_and_blocks_reapproval(ready):
    with Session(ready) as db:
        authorize_submission(db, 1, "test-token", quote())
        update_supplier_order(db, db.get(SupplierOrder, 1), {"status": "failed"})
        reservation = db.scalar(select(PurchaseReservation))
        assert reservation.status == "uncertain" and reservation.amount_cents == 1000


def test_confirmation_cannot_change_reserved_total(ready):
    with Session(ready) as db:
        authorize_submission(db, 1, "test-token", quote())
        with pytest.raises(ValueError, match="budget reservation"):
            update_supplier_order(db, db.get(SupplierOrder, 1),
                {"status": "placed", "external_order_id": "HD-123", "total": 10.01})
        db.rollback()
        assert db.scalar(select(PurchaseReservation)).status == "submitting"


def test_legacy_approval_cannot_submit(ready):
    with Session(ready) as db:
        db.delete(db.scalar(select(AppSetting).where(AppSetting.key == "owner_place_order:1")))
        db.commit()
        with pytest.raises(ValueError, match="Use Place Order"):
            authorize_submission(db, 1, "test-token", quote())
        db.rollback()
        assert db.scalar(select(PurchaseReservation)) is None


def test_permission_from_previous_approval_cannot_submit(ready):
    with Session(ready) as db:
        db.get(SupplierOrder, 1).approved_at += timedelta(seconds=1)
        db.commit()
        with pytest.raises(ValueError, match="Use Place Order"):
            authorize_submission(db, 1, "test-token", quote())


def test_place_order_click_records_permission_and_legacy_approval_does_not(ready, monkeypatch):
    from app.services.fulfillment import approve_supplier_order, require_owner_place_order
    monkeypatch.setattr("app.services.fulfillment._readiness_issues", lambda row: [])
    with Session(ready) as db:
        row = db.get(SupplierOrder, 1)
        row.status = "draft"
        db.commit()
        row = approve_supplier_order(db, 1)
        with pytest.raises(ValueError, match="Use Place Order"):
            require_owner_place_order(db, row)
        row.status = "draft"
        db.commit()
        row = approve_supplier_order(db, 1, owner_click=True)
        require_owner_place_order(db, row)
        assert row.status == "queued"


def test_legacy_queue_returns_to_draft_without_checkout_lease(ready):
    from app.services.fulfillment import claim_next_supplier_order
    with Session(ready) as db:
        row = db.get(SupplierOrder, 1)
        row.status = "queued"
        row.checkout_token = ""
        db.delete(db.scalar(select(AppSetting).where(AppSetting.key == "owner_place_order:1")))
        db.commit()
        assert claim_next_supplier_order(db) is None
        assert db.get(SupplierOrder, 1).status == "draft"
        assert not db.get(SupplierOrder, 1).checkout_token

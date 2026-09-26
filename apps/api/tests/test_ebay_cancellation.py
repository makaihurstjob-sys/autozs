from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.database import Base
from app.models.domain import Order, SupplierOrder, FulfillmentTask
from app.services.orders import _normalize_order_row, _order_status, import_ebay_order_report_rows, reconcile_ebay_cancellation
from app.services.fulfillment import approve_supplier_order, claim_next_supplier_order


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def seed(db, status="draft", purchased=False):
    order = Order(ebay_order_id="04-15204-72108", account_id="test", status="imported", total=28.53)
    supplier = SupplierOrder(order=order, status=status, external_order_id="RECEIPT" if purchased else "", checkout_token="lease", lease_expires_at=datetime.utcnow()+timedelta(minutes=5))
    order.fulfillment_tasks.append(FulfillmentTask(status="open"))
    db.add(order)
    db.commit()
    return order, supplier


def report(db, cancel_status=None):
    row = {"Order Number": "04-15204-72108", "Item Title": "Fertilizer", "Order Status": "Paid", "Paid On Date": "Sep-20-26", "Total Price": "28.53"}
    if cancel_status is not None:
        row["Cancel Status"] = cancel_status
    return import_ebay_order_report_rows(db, rows=[row], account_key="test")


@pytest.mark.parametrize("column", ["Order Status", "Status", "Cancel Status"])
def test_cancellation_in_any_column_overrides_paid(column):
    row = {"Order Status": "Paid", "Status": "Paid", "Paid On Date": "Sep-20-26", column: "Canceled"}
    assert _order_status([_normalize_order_row(row)]) == "cancelled"


@pytest.mark.parametrize("value", ["Not canceled", "Not cancelled", "No cancellation", "Cancellation rejected"])
def test_negative_cancellation_label_is_not_a_cancellation(value):
    row = {"Cancel Status": value, "Paid On Date": "Sep-20-26"}
    assert _order_status([_normalize_order_row(row)]) == "imported"


def test_report_cancels_existing_fulfillment_and_does_not_reopen(db):
    order, supplier = seed(db, "queued")
    report(db, "Canceled")
    assert order.status == "cancelled"
    assert order.fulfillment_tasks[0].status == "blocked"
    assert supplier.status == "cancelled"
    assert supplier.checkout_token == ""
    assert supplier.lease_expires_at is None
    report(db)  # Older/incomplete report still says paid.
    assert order.status == "cancelled"
    assert supplier.status == "cancelled"
    assert "reports cancellation" in order.fulfillment_tasks[0].note
    assert claim_next_supplier_order(db) is None
    with pytest.raises(ValueError, match="cancelled"):
        approve_supplier_order(db, supplier.id)


@pytest.mark.parametrize("status", ["queued", "placing"])
def test_approval_checks_parent_before_idempotent_return(db, status):
    order, supplier = seed(db, status)
    order.status = "cancelled"
    db.commit()
    with pytest.raises(ValueError, match="cancelled"):
        approve_supplier_order(db, supplier.id)


def test_cancelled_supplier_cannot_be_reapproved_when_parent_stale(db):
    order, supplier = seed(db, "cancelled")
    with pytest.raises(ValueError, match="Cancelled supplier"):
        approve_supplier_order(db, supplier.id)


def test_cancellation_preserves_recorded_supplier_purchase(db):
    order, supplier = seed(db, "placed", purchased=True)
    reconcile_ebay_cancellation(db, order, evidence="Verified Seller Hub page")
    db.commit()
    assert supplier.status == "placed"
    assert supplier.external_order_id == "RECEIPT"
    assert "reconcile separately" in supplier.failure_reason
    assert order.fulfillment_tasks[0].status == "blocked"


def test_inflight_checkout_is_held_for_reconciliation(db):
    order, supplier = seed(db, "placing")
    reconcile_ebay_cancellation(db, order, evidence="Verified Seller Hub page")
    db.commit()
    assert supplier.status == "needs_review"
    assert supplier.checkout_token == ""
    assert supplier.lease_expires_at is None
    with pytest.raises(ValueError, match="cancelled"):
        approve_supplier_order(db, supplier.id)


def test_direct_observation_evidence_survives_incomplete_sync(db):
    order, supplier = seed(db)
    reconcile_ebay_cancellation(db, order, evidence="Seller Hub checked at 2026-09-26T16:04:31Z")
    db.commit()
    report(db)
    assert "2026-09-26T16:04:31Z" in order.fulfillment_tasks[0].note
    assert "2026-09-26T16:04:31Z" in supplier.failure_reason


def test_new_cancelled_order_has_one_blocked_task_with_autoflush_disabled(db):
    db.autoflush = False
    report(db, "Canceled")
    order = db.query(Order).one()
    assert len(order.fulfillment_tasks) == 1
    assert order.fulfillment_tasks[0].status == "blocked"
    assert not order.supplier_orders

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from threading import Barrier

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.domain import (Order, SupplierOrder, PurchaseReservation,
                               PurchaseBudgetLock, SupplierPurchaseAttempt,
                               SupplierOrderItem, GiftCard)
from app.services.purchase_budget import reserve, begin_submission, record_outcome, budget_day
from app.services.purchase_policy import PurchaseEvaluation


TODAY = datetime(2026, 9, 26, 18, tzinfo=timezone.utc)
TOMORROW = datetime(2026, 9, 27, 18, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'budget.db'}", connect_args={"timeout": 10})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        # Disposable test database only; avoid fsync for hundreds of schema DDLs.
        connection.execute("PRAGMA synchronous=OFF")
    Base.metadata.create_all(engine, tables=[model.__table__ for model in (
        Order, GiftCard, SupplierOrder, SupplierOrderItem, SupplierPurchaseAttempt,
        PurchaseBudgetLock, PurchaseReservation,
    )])
    with Session(engine) as db, db.begin():
        for number in range(1, 5):
            db.add(Order(id=number, ebay_order_id=f"test-{number}"))
        db.flush()
        for number in range(1, 5):
            db.add(SupplierOrder(id=number, order_id=number))
        db.add(SupplierOrder(id=5, order_id=1))
    yield engine
    engine.dispose()


def add(db, number, amount=6000, now=TODAY, supplier=None):
    return reserve(db, order_id=number, supplier_order_id=supplier or number,
                   evaluation=PurchaseEvaluation(amount, 25), now=now)


def test_concurrent_orders_cannot_overspend(engine):
    barrier = Barrier(2)
    def attempt(number):
        barrier.wait()
        with Session(engine) as db:
            try:
                add(db, number)
                db.commit()
                return "reserved"
            except ValueError as exc:
                db.rollback()
                assert "daily budget" in str(exc)
                return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, [1, 2])) == ["blocked", "reserved"]
    with Session(engine) as db:
        assert len(db.scalars(select(PurchaseReservation)).all()) == 1


def test_uncertain_survives_reconnect_and_next_day(engine):
    with Session(engine) as db, db.begin():
        add(db, 1)
        begin_submission(db, 1)
        record_outcome(db, 1)
    engine.dispose()
    with Session(engine) as db, pytest.raises(ValueError, match="daily budget"):
        add(db, 2, now=TOMORROW)


def test_duplicate_marketplace_order_blocked_across_drafts(engine):
    with Session(engine) as db, db.begin():
        add(db, 1)
    with Session(engine) as db, pytest.raises(ValueError, match="already reserved"):
        add(db, 1, supplier=5)


def test_submission_permission_is_one_shot(engine):
    with Session(engine) as db, db.begin():
        add(db, 1)
        begin_submission(db, 1)
    with Session(engine) as db, pytest.raises(ValueError, match="already attempted"):
        begin_submission(db, 1)


def test_purchased_amount_counts_today_but_not_tomorrow(engine):
    with Session(engine) as db, db.begin():
        add(db, 1)
        begin_submission(db, 1)
        record_outcome(db, 1, confirmation="HD-123", now=TODAY)
    with Session(engine) as db, pytest.raises(ValueError, match="daily budget"):
        add(db, 2)
    with Session(engine) as db, db.begin():
        add(db, 2, now=TOMORROW)
    with Session(engine) as db, pytest.raises(ValueError, match="already reserved"):
        add(db, 1, now=TOMORROW)


def test_rollback_does_not_consume_budget(engine):
    with Session(engine) as db:
        add(db, 1)
        db.rollback()
    with Session(engine) as db, db.begin():
        add(db, 2, amount=10000)


def test_conflicting_confirmation_cannot_rewrite_spend_day(engine):
    with Session(engine) as db, db.begin():
        add(db, 1)
        begin_submission(db, 1)
        record_outcome(db, 1, confirmation="HD-123", now=TODAY)
    with Session(engine) as db, db.begin():
        record_outcome(db, 1, confirmation="HD-123", now=TOMORROW)
        assert db.scalar(select(PurchaseReservation)).spent_day == "2026-09-26"
    with Session(engine) as db, pytest.raises(ValueError, match="Conflicting"):
        record_outcome(db, 1, confirmation="different", now=TOMORROW)


def test_budget_day_uses_chicago_midnight():
    assert budget_day(datetime(2026, 9, 27, 4, 59, tzinfo=timezone.utc)) == "2026-09-26"
    assert budget_day(datetime(2026, 9, 27, 5, 0, tzinfo=timezone.utc)) == "2026-09-27"
    with pytest.raises(ValueError, match="timezone"):
        budget_day(datetime(2026, 9, 27))


def test_existing_manual_purchase_consumes_daily_budget(engine):
    with Session(engine) as db, db.begin():
        supplier = db.get(SupplierOrder, 1)
        supplier.status = "placed"
        supplier.total = 60
        supplier.placed_at = TODAY.replace(tzinfo=None)
    with Session(engine) as db, pytest.raises(ValueError, match="daily budget"):
        add(db, 2)


def test_reservation_cannot_use_another_orders_draft(engine):
    with Session(engine) as db, pytest.raises(ValueError, match="does not belong"):
        add(db, 1, supplier=2)


def test_checkout_approval_and_claim_block_reserved_order(engine):
    from app.services.fulfillment import approve_supplier_order, claim_next_supplier_order
    with Session(engine) as db, db.begin():
        add(db, 1)
        db.get(SupplierOrder, 1).status = "queued"
    with Session(engine) as db, pytest.raises(ValueError, match="already reserved"):
        approve_supplier_order(db, 1)
    with Session(engine) as db:
        assert claim_next_supplier_order(db) is None


def test_only_matching_active_checkout_can_reserve_its_preparation(engine):
    with Session(engine) as db, db.begin():
        supplier = db.get(SupplierOrder, 1)
        supplier.status = "placing"
        supplier.checkout_token = "test-lease"
        supplier.approved_total = 60
        supplier.lease_expires_at = (TODAY + timedelta(minutes=5)).replace(tzinfo=None)
    with Session(engine) as db, pytest.raises(ValueError, match="unresolved checkout"):
        add(db, 1)
    with Session(engine) as db, db.begin():
        reserve(db, order_id=1, supplier_order_id=1, evaluation=PurchaseEvaluation(6000, 25),
                now=TODAY, checkout_token="test-lease")
        begin_submission(db, 1)

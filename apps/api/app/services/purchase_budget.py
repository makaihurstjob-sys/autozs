"""Transactional supplier budget ledger. Callers commit before external actions.

Unresolved reservations count on every day, including after a process restart.
Neither a timeout nor a local cancellation releases money automatically.
"""
from datetime import datetime, timezone
import hmac
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.models.domain import PurchaseBudgetLock, PurchaseReservation, SupplierOrder, SupplierPurchaseAttempt
from app.services.purchase_policy import BuyingLimits, PurchaseEvaluation, cents


def budget_day(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Budget time must include timezone")
    return now.astimezone(ZoneInfo("America/Chicago")).date().isoformat()


def _lock(db: Session) -> None:
    # Acquire the SQLite writer lock BEFORE reading balances. This also handles
    # simultaneous first use; an in-process mutex cannot protect other workers.
    if db.get_bind().dialect.name != "sqlite":
        raise ValueError("Purchase budget locking is only configured for SQLite")
    db.execute(insert(PurchaseBudgetLock).values(id=1, version=0).on_conflict_do_nothing())
    db.execute(update(PurchaseBudgetLock).where(PurchaseBudgetLock.id == 1)
               .values(version=PurchaseBudgetLock.version + 1))


def reserve(db: Session, *, order_id: int, supplier_order_id: int,
            evaluation: PurchaseEvaluation, limits: BuyingLimits = BuyingLimits(),
            now: datetime | None = None, checkout_token: str = "") -> PurchaseReservation:
    now = now or datetime.now(timezone.utc)
    day = budget_day(now)
    amount = evaluation.supplier_total_cents
    if type(amount) is not int or amount <= 0 or amount > limits.per_order_cents:
        raise ValueError("Invalid reservation amount or per-order limit exceeded")
    if evaluation.net_profit_cents < limits.minimum_profit_cents:
        raise ValueError("Minimum net profit not met")
    _lock(db)
    supplier = db.get(SupplierOrder, supplier_order_id)
    if supplier is None or supplier.order_id != order_id:
        raise ValueError("Supplier draft does not belong to the marketplace order")
    rows = db.scalars(select(PurchaseReservation).execution_options(populate_existing=True)).all()
    if any(row.order_id == order_id or row.supplier_order_id == supplier_order_id for row in rows):
        raise ValueError("Order already reserved; reconcile before another purchase")
    used = sum(row.amount_cents for row in rows
               if row.status != "purchased" or row.spent_day == day)
    represented = {row.supplier_order_id for row in rows}
    unresolved = set(db.scalars(select(SupplierPurchaseAttempt.supplier_order_id).where(
        SupplierPurchaseAttempt.status.in_(["started", "uncertain"])
    )).all())
    # Existing/manual purchases must also consume the shared cap. Unknown dates
    # or unfinished legacy attempts remain held until explicitly reconciled.
    for previous in db.scalars(select(SupplierOrder)).all():
        if previous.id in represented:
            continue
        purchased = bool(previous.external_order_id or previous.placed_at or
                         previous.status in {"placed", "shipped", "delivered"})
        pending = previous.status == "placing" or previous.id in unresolved
        if not purchased and not pending:
            continue
        if (previous.id == supplier_order_id and not purchased
                and previous.status == "placing" and checkout_token
                and previous.checkout_token
                and hmac.compare_digest(checkout_token, previous.checkout_token)
                and previous.lease_expires_at is not None
                and previous.lease_expires_at.replace(tzinfo=timezone.utc) > now):
            # The current authenticated preparation lease has not submitted yet.
            # All older/expired attempts still block the order below.
            older_uncertain = db.scalar(select(SupplierPurchaseAttempt.id).where(
                SupplierPurchaseAttempt.supplier_order_id == supplier_order_id,
                SupplierPurchaseAttempt.status == "uncertain",
            ))
            if older_uncertain is None:
                continue
        if previous.order_id == order_id:
            raise ValueError("Order has an existing purchase or unresolved checkout")
        spent_day = (budget_day(previous.placed_at.replace(tzinfo=timezone.utc))
                     if previous.placed_at else None)
        if pending or spent_day is None or spent_day == day:
            cost = cents(previous.total if purchased else previous.approved_total, "Existing purchase total")
            if cost <= 0:
                raise ValueError("Existing purchase amount is unknown")
            used += cost
    if used + amount > limits.daily_cents:
        raise ValueError("Remaining daily budget exceeded")
    row = PurchaseReservation(order_id=order_id, supplier_order_id=supplier_order_id,
                              amount_cents=amount, status="reserved")
    db.add(row)
    db.flush()
    return row


def require_unreserved(db: Session, order_id: int) -> None:
    if db.scalar(select(PurchaseReservation.id).where(PurchaseReservation.order_id == order_id)) is not None:
        raise ValueError("Purchase budget already reserved; reconcile before retrying checkout")


def begin_submission(db: Session, supplier_order_id: int) -> None:
    """One-shot transition; repeated requests never grant another submission."""
    _lock(db)
    result = db.execute(update(PurchaseReservation).where(
        PurchaseReservation.supplier_order_id == supplier_order_id,
        PurchaseReservation.status == "reserved",
    ).values(status="submitting"))
    if result.rowcount != 1:
        raise ValueError("Submission already attempted or budget not reserved")


def record_outcome(db: Session, supplier_order_id: int, *, confirmation: str = "",
                   now: datetime | None = None) -> None:
    _lock(db)
    row = db.scalar(select(PurchaseReservation).where(
        PurchaseReservation.supplier_order_id == supplier_order_id
    ).execution_options(populate_existing=True))
    if row is None or row.status == "reserved":
        raise ValueError("No submission to reconcile")
    if row.status == "purchased":
        if confirmation != row.evidence:
            raise ValueError("Conflicting purchase confirmation")
        return
    if confirmation.strip():
        row.status = "purchased"
        row.spent_day = budget_day(now)
        row.evidence = confirmation.strip()
    else:
        row.status = "uncertain"
    db.flush()

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.domain import (
    BalanceSnapshot,
    FinanceEntry,
    FinancialAccount,
    GiftCard,
    Order,
    SubscriptionExpense,
    SupplierOrder,
)


def upsert_financial_account(db: Session, values: dict) -> FinancialAccount:
    account = db.scalar(
        select(FinancialAccount).where(
            FinancialAccount.provider == values["provider"],
            FinancialAccount.external_id == values["external_id"],
        )
    )
    if account is None:
        account = FinancialAccount(provider=values["provider"], external_id=values["external_id"])
        db.add(account)
    for field, value in values.items():
        setattr(account, field, value)
    account.last_synced_at = account.last_synced_at or datetime.utcnow()
    db.flush()
    db.add(
        BalanceSnapshot(
            financial_account_id=account.id,
            current_balance=account.current_balance,
            available_balance=account.available_balance,
            held_balance=account.held_balance,
            captured_at=account.last_synced_at,
        )
    )
    db.commit()
    db.refresh(account)
    return account


def create_subscription(db: Session, values: dict) -> SubscriptionExpense:
    subscription = SubscriptionExpense(**values)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def import_finance_entries(db: Session, entries: list[dict]) -> int:
    imported = 0
    for values in entries:
        existing = db.scalar(
            select(FinanceEntry).where(
                FinanceEntry.provider == values["provider"],
                FinanceEntry.external_id == values["external_id"],
            )
        )
        if existing is not None:
            continue
        db.add(FinanceEntry(**values))
        imported += 1
    db.commit()
    return imported


def finance_overview(db: Session) -> dict:
    orders = list(db.scalars(select(Order).where(Order.status != "cancelled")).all())
    supplier_orders = list(
        db.scalars(
            select(SupplierOrder)
            .options(selectinload(SupplierOrder.gift_card))
            .where(SupplierOrder.status.in_(["placed", "shipped", "delivered"]))
        ).all()
    )
    entries = list(db.scalars(select(FinanceEntry)).all())
    accounts = list(db.scalars(select(FinancialAccount).order_by(FinancialAccount.account_type, FinancialAccount.name)).all())
    subscriptions = list(db.scalars(select(SubscriptionExpense).order_by(SubscriptionExpense.status, SubscriptionExpense.name)).all())
    cards = list(db.scalars(select(GiftCard)).all())

    revenue = round(sum(float(order.total or 0) for order in orders), 2)
    supplier_cost = round(sum(_cash_supplier_cost(order) for order in supplier_orders), 2)
    operating_expenses = round(
        sum(abs(float(entry.amount)) for entry in entries if entry.entry_type in {"expense", "fee"}),
        2,
    )
    period_rows: dict[str, dict] = defaultdict(lambda: {"revenue": 0.0, "supplier_cost": 0.0, "operating_expenses": 0.0, "orders": 0})
    for order in orders:
        for period in _periods(order.created_at):
            period_rows[period]["revenue"] += float(order.total or 0)
            period_rows[period]["orders"] += 1
    for order in supplier_orders:
        for period in _periods(order.placed_at or order.created_at):
            period_rows[period]["supplier_cost"] += _cash_supplier_cost(order)
    for entry in entries:
        if entry.entry_type in {"expense", "fee"}:
            for period in _periods(entry.occurred_at):
                period_rows[period]["operating_expenses"] += abs(float(entry.amount))

    periods = [{
        "period": "All time",
        "revenue": revenue,
        "supplier_cost": supplier_cost,
        "operating_expenses": operating_expenses,
        "profit": round(revenue - supplier_cost - operating_expenses, 2),
        "orders": len(orders),
    }]
    for period in sorted(period_rows, reverse=True):
        row = period_rows[period]
        periods.append(
            {
                "period": period,
                "revenue": round(row["revenue"], 2),
                "supplier_cost": round(row["supplier_cost"], 2),
                "operating_expenses": round(row["operating_expenses"], 2),
                "profit": round(row["revenue"] - row["supplier_cost"] - row["operating_expenses"], 2),
                "orders": row["orders"],
            }
        )
    return {
        "revenue": revenue,
        "supplier_cost": supplier_cost,
        "operating_expenses": operating_expenses,
        "profit": round(revenue - supplier_cost - operating_expenses, 2),
        "gift_card_face_balance": round(sum(float(card.current_balance or 0) for card in cards if card.status == "active"), 2),
        "gift_card_cash_basis": round(sum(_remaining_card_cash_basis(card) for card in cards if card.status == "active"), 2),
        "bank_balance": round(sum(float(account.current_balance or 0) for account in accounts if account.account_type == "bank"), 2),
        "credit_card_balance": round(sum(float(account.current_balance or 0) for account in accounts if account.account_type == "credit_card"), 2),
        "ebay_available": round(sum(float(account.available_balance or 0) for account in accounts if account.account_type == "ebay"), 2),
        "ebay_held": round(sum(float(account.held_balance or 0) for account in accounts if account.account_type == "ebay"), 2),
        "accounts": accounts,
        "subscriptions": subscriptions,
        "periods": periods,
    }


def _cash_supplier_cost(order: SupplierOrder) -> float:
    gift_amount = float(order.gift_card_amount or 0)
    card_amount = float(order.card_amount or 0)
    card = order.gift_card
    if card is None or float(card.face_value or 0) <= 0:
        return round(gift_amount + card_amount, 2)
    ratio = float(card.acquisition_cost or 0) / float(card.face_value)
    return round(gift_amount * ratio + card_amount, 2)


def _remaining_card_cash_basis(card: GiftCard) -> float:
    if float(card.face_value or 0) <= 0:
        return 0.0
    return float(card.current_balance or 0) * float(card.acquisition_cost or 0) / float(card.face_value)


def _periods(value: datetime | None) -> tuple[str, str]:
    if value is None:
        return ("Month Unknown", "Week Unknown")
    iso = value.isocalendar()
    return (f"Month {value:%Y-%m}", f"Week {iso.year}-W{iso.week:02d}")

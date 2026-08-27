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
from app.services.settings import read_pricing_settings


FULFILLED_ORDER_STATUSES = {"shipped", "delivered", "completed"}
PLACED_SUPPLIER_ORDER_STATUSES = {"placed", "shipped", "delivered"}


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


def record_order_ebay_fee(db: Session, order: Order, *, fee_amount: float, evidence_ref: str) -> Order:
    clean_evidence = str(evidence_ref or "").strip()
    if not clean_evidence:
        raise ValueError("An evidence reference (the eBay order/transaction id the fee was read from) is required.")
    if float(fee_amount) < 0:
        raise ValueError("eBay fee amount cannot be negative.")
    order.ebay_fee_amount = round(float(fee_amount), 2)
    order.ebay_fee_evidence_ref = clean_evidence
    order.ebay_fee_recorded_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order


def finance_overview(db: Session) -> dict:
    orders = list(db.scalars(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.supplier_orders).selectinload(SupplierOrder.gift_card))
        .where(Order.status != "cancelled")
    ).all())
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
    pricing = read_pricing_settings(db)

    revenue = round(sum(float(order.total or 0) for order in orders), 2)
    supplier_cost = round(sum(_cash_supplier_cost(order) for order in supplier_orders), 2)
    operating_expenses = round(
        sum(abs(float(entry.amount)) for entry in entries if entry.entry_type in {"expense", "fee"}),
        2,
    )
    gross_merchandise_revenue = round(sum(_order_merchandise_revenue(order) for order in orders), 2)
    fulfilled_orders = [order for order in orders if _is_realized_order(order)]
    realized_revenue = round(sum(_order_merchandise_revenue(order) for order in fulfilled_orders), 2)
    marketplace_rate = float(pricing.get("default_ebay_fee_rate", 0.0) or 0.0) + float(
        pricing.get("default_promoted_rate", 0.0) or 0.0
    )
    return_risk_rate = float(pricing.get("default_return_risk_rate", 0.0) or 0.0)
    estimated_marketplace_fees = round(realized_revenue * marketplace_rate, 2)
    return_risk_reserve = round(realized_revenue * return_risk_rate, 2)
    realized_supplier_orders = [
        supplier_order
        for order in fulfilled_orders
        for supplier_order in order.supplier_orders
        if str(supplier_order.status or "").lower() in PLACED_SUPPLIER_ORDER_STATUSES
    ]
    missing_supplier_cost_orders = [
        order for order in fulfilled_orders
        if _order_merchandise_revenue(order) > 0
        and not any(str(item.status or "").lower() in PLACED_SUPPLIER_ORDER_STATUSES for item in order.supplier_orders)
    ]
    # Real per-order eBay fees only -- never the rate-based estimate above and
    # never a generic imported ledger entry, so verified_profit can't be built
    # on a number nobody can trace back to an actual eBay transaction.
    fee_missing_orders = [
        order for order in fulfilled_orders
        if _order_merchandise_revenue(order) > 0 and order.ebay_fee_amount is None
    ]
    recorded_fee_expenses = round(sum(
        float(order.ebay_fee_amount or 0) for order in fulfilled_orders if order.ebay_fee_amount is not None
    ), 2)
    non_fee_expenses = round(sum(
        abs(float(entry.amount)) for entry in entries if entry.entry_type == "expense"
    ), 2)
    issues: list[str] = []
    if missing_supplier_cost_orders:
        issues.append(f"{len(missing_supplier_cost_orders)} fulfilled order(s) are missing a placed supplier order and verified supplier cost.")
    if fee_missing_orders:
        issues.append(f"{len(fee_missing_orders)} fulfilled order(s) are missing a recorded actual eBay fee.")
    # Available funds come from Robinhood specifically -- z_finance (or any
    # other provider) never counts here, per the corrected accounting rules.
    robinhood_accounts = [account for account in accounts if account.provider == "robinhood"]
    fresh_robinhood_accounts = [account for account in robinhood_accounts if account.last_synced_at]
    if not fresh_robinhood_accounts:
        issues.append("No verified Robinhood balance is connected.")
    elif any((datetime.utcnow() - account.last_synced_at).total_seconds() > 48 * 3600 for account in fresh_robinhood_accounts):
        issues.append("The connected Robinhood balance is older than 48 hours.")
    profit_verified = realized_revenue > 0 and not issues
    verified_profit = None
    available_business_profit = 0.0
    if profit_verified:
        realized_supplier_cost = round(sum(_cash_supplier_cost(order) for order in realized_supplier_orders), 2)
        verified_profit = round(
            realized_revenue - realized_supplier_cost - recorded_fee_expenses - non_fee_expenses - return_risk_reserve,
            2,
        )
        liquid_balance = round(sum(
            float(account.available_balance if account.available_balance is not None else account.current_balance or 0)
            for account in fresh_robinhood_accounts
        ), 2)
        available_business_profit = round(max(0.0, min(verified_profit, liquid_balance)), 2)
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
        "gross_merchandise_revenue": gross_merchandise_revenue,
        "realized_revenue": realized_revenue,
        "estimated_marketplace_fees": estimated_marketplace_fees,
        "return_risk_reserve": return_risk_reserve,
        "verified_profit": verified_profit,
        "available_business_profit": available_business_profit,
        "profit_verified": profit_verified,
        "unverified_order_count": len({order.id for order in missing_supplier_cost_orders} | {order.id for order in fee_missing_orders}),
        "profit_data_issues": issues,
        "accounts": accounts,
        "subscriptions": subscriptions,
        "periods": periods,
}


def _order_merchandise_revenue(order: Order) -> float:
    item_revenue = sum(float(item.sale_price or 0) * max(1, int(item.quantity or 1)) for item in order.items)
    return item_revenue if item_revenue > 0 else float(order.total or 0)


def _is_realized_order(order: Order) -> bool:
    if str(order.status or "").lower() in FULFILLED_ORDER_STATUSES:
        return True
    return any(str(item.status or "").lower() in PLACED_SUPPLIER_ORDER_STATUSES for item in order.supplier_orders)


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

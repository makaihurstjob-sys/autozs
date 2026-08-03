from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.core.store_keys import DEFAULT_EBAY_STORE_KEY, normalize_store_key
from app.models.domain import BalanceSnapshot, FinancialAccount, Order, SupplierOrder
from app.models.z_finance import ZFinancePayout, ZFinanceSyncState, ZFinanceTransaction

CLASSIFICATIONS = {
    "supplier_charge", "ebay_fee", "refund", "subscription",
    "payout", "transfer", "card_payment",
}
EXCLUDED = {"transfer", "card_payment"}
OUTFLOWS = {"supplier_charge", "ebay_fee", "refund", "subscription", "card_payment"}
ACCOUNT_FIELDS = {
    "id", "accountId", "name", "type", "subtype", "currentBalance",
    "availableBalance", "currency", "updatedAt", "storeKey", "role",
}
TRANSACTION_FIELDS = {
    "id", "accountId", "amount", "direction", "classification", "merchant",
    "description", "postedAt", "pending", "currency", "supplierOrderReference",
    "ebayOrderReference", "payoutReference", "storeKey",
}
PAYOUT_FIELDS = {
    "id", "payoutId", "amount", "currency", "status", "payoutAt", "date",
    "storeKey", "account",
}
WRAPPER_FIELDS = {
    "data", "accounts", "transactions", "payouts", "nextCursor", "hasMore", "storeKey",
    "count",
}
SENSITIVE_FIELD_FRAGMENTS = {
    "access_token", "accesstoken", "plaid", "routing", "account_number",
    "accountnumber", "payment_details", "paymentdetails", "buyer_address",
    "buyeraddress", "webhook",
}


def validate_client_config(settings: Settings | None = None) -> tuple[str, str, set[str]]:
    settings = settings or get_settings()
    parsed = urlsplit(settings.z_finance_base_url.strip())
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Z_FINANCE_BASE_URL must be a clean HTTPS origin")
    if not settings.z_finance_autozs_token:
        raise ValueError("Z_FINANCE_AUTOZS_TOKEN is not configured")
    ids = {
        settings.z_finance_operating_account_id.strip(),
        settings.z_finance_purchasing_card_id.strip(),
    }
    if "" in ids or len(ids) != 2:
        raise ValueError("Z Finance account IDs must be present and distinct")
    return f"{parsed.scheme}://{parsed.netloc}", settings.z_finance_autozs_token, ids


class ZFinanceClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        allowed_account_ids: set[str],
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.allowed_account_ids = allowed_account_ids
        self._owned_client = client is None
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    def get_accounts(self) -> list[dict]:
        response = self._client.get(
            f"{self.base_url}/integrations/autozs/accounts",
            headers=self._headers,
        )
        response.raise_for_status()
        body = response.json()
        accounts = _extract_list(body, "accounts")
        validate_accounts_contract(body, accounts, self.allowed_account_ids)
        return accounts

    def iter_transaction_pages(
        self,
        *,
        cursor: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        current_cursor = cursor
        while True:
            params: dict[str, str] = {}
            if current_cursor:
                params["cursor"] = current_cursor
            if start_date:
                params["startDate"] = start_date.isoformat()
            if end_date:
                params["endDate"] = end_date.isoformat()
            response = self._client.get(
                f"{self.base_url}/integrations/autozs/transactions",
                headers=self._headers,
                params=params,
            )
            response.raise_for_status()
            body = _unwrap(response.json())
            transactions = _extract_list(body, "transactions")
            payouts = _extract_list(body, "payouts")
            validate_transactions_contract(body, transactions, payouts, self.allowed_account_ids)
            next_cursor = body.get("nextCursor") if isinstance(body, dict) else None
            has_more = body.get("hasMore") is True if isinstance(body, dict) else False
            yield transactions, payouts, (str(next_cursor) if next_cursor else None)
            if not has_more:
                break
            if not next_cursor or str(next_cursor) == current_cursor:
                raise ValueError("Z Finance pagination declared hasMore without a new nextCursor")
            current_cursor = str(next_cursor)


def validate_accounts_contract(body, accounts: list[dict], allowed_ids: set[str]) -> None:
    _validate_wrapper(body)
    _validate_store_keys(body, accounts)
    _validate_item_fields(accounts, ACCOUNT_FIELDS, "account")
    returned_ids = {str(item.get("id") or item.get("accountId") or "") for item in accounts}
    if returned_ids != allowed_ids or len(accounts) != len(allowed_ids):
        raise ValueError("Z Finance account response must contain exactly the configured accounts")


def validate_transactions_contract(
    body,
    transactions: list[dict],
    payouts: list[dict],
    allowed_ids: set[str],
) -> None:
    _validate_wrapper(body)
    _validate_store_keys(body, transactions, payouts)
    _validate_item_fields(transactions, TRANSACTION_FIELDS, "transaction")
    _validate_item_fields(payouts, PAYOUT_FIELDS, "payout")
    for item in transactions:
        account_id = str(item.get("accountId") or "")
        if account_id not in allowed_ids:
            raise ValueError("Z Finance transaction belongs to an unexpected account")
        if str(item.get("direction") or "").lower() not in {"inflow", "outflow"}:
            raise ValueError("Z Finance transaction direction must be inflow or outflow")
        if str(item.get("classification") or "").lower() not in CLASSIFICATIONS:
            raise ValueError("Z Finance transaction classification is not supported")


def _validate_wrapper(body) -> None:
    value = body
    while isinstance(value, dict):
        unexpected = set(value) - WRAPPER_FIELDS
        if unexpected and any(key in value for key in ("data", "accounts", "transactions", "payouts")):
            raise ValueError("Z Finance response wrapper contains unrecognized fields")
        if not isinstance(value.get("data"), (dict, list)):
            break
        value = value["data"]
    _reject_sensitive_fields(body)


def _validate_item_fields(items: list[dict], allowed_fields: set[str], kind: str) -> None:
    for item in items:
        if set(item) - allowed_fields:
            raise ValueError(f"Z Finance {kind} contains unrecognized fields")


def _validate_store_keys(*values) -> None:
    for value in values:
        if isinstance(value, dict):
            if "storeKey" in value and value["storeKey"] != DEFAULT_EBAY_STORE_KEY:
                raise ValueError("Z Finance store key must be exactly a.m.anim-59")
            _validate_store_keys(*value.values())
        elif isinstance(value, list):
            _validate_store_keys(*value)


def _reject_sensitive_fields(value) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(fragment in normalized for fragment in SENSITIVE_FIELD_FRAGMENTS):
                raise ValueError("Z Finance response contains a prohibited sensitive field")
            _reject_sensitive_fields(nested)
    elif isinstance(value, list):
        for item in value:
            _reject_sensitive_fields(item)


def period_bounds(period: str, start_date: date | None, end_date: date | None) -> tuple[datetime | None, datetime | None]:
    if period not in {"all", "monthly", "weekly", "custom"}:
        raise ValueError("period must be all, monthly, weekly, or custom")
    end_day = end_date or date.today()
    if period == "all":
        return None, None
    if period == "custom":
        if not start_date or not end_date:
            raise ValueError("custom period requires startDate and endDate")
        if start_date > end_date:
            raise ValueError("startDate must not be after endDate")
        first = start_date
    elif period == "weekly":
        first = end_day - timedelta(days=end_day.weekday())
    else:
        first = end_day.replace(day=1)
    return datetime.combine(first, time.min), datetime.combine(end_day, time.max)


def sync_from_z_finance(
    db: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    reset_cursor: bool = False,
    client: httpx.Client | None = None,
) -> dict:
    settings = get_settings()
    base_url, token, allowed_ids = validate_client_config(settings)
    state = db.scalar(select(ZFinanceSyncState).where(ZFinanceSyncState.provider == "z_finance"))
    if state is None:
        state = ZFinanceSyncState(provider="z_finance")
        db.add(state)
        db.flush()
    cursor = None if reset_cursor else state.cursor
    finance_client = ZFinanceClient(base_url, token, allowed_ids, client=client)
    account_count = transaction_count = payout_count = 0
    try:
        accounts = finance_client.get_accounts()
        for payload in accounts:
            external_id = str(payload.get("id") or payload.get("accountId") or "")
            _upsert_account(db, payload, external_id, settings)
            account_count += 1

        for transactions, payouts, next_cursor in finance_client.iter_transaction_pages(
            cursor=cursor,
            start_date=start_date,
            end_date=end_date,
        ):
            for payout in payouts:
                _upsert_payout(db, payout)
                payout_count += 1
            for payload in transactions:
                external_id = str(payload.get("id") or "")
                account_id = str(payload.get("accountId") or payload.get("account_id") or "")
                if not external_id:
                    raise ValueError("Z Finance transaction ID is required")
                _upsert_transaction(db, payload, external_id, account_id)
                transaction_count += 1
            db.flush()
            _reconcile(db)
            db.commit()
            # Cursor is durable only after the page and its reconciliation committed.
            state = db.scalar(select(ZFinanceSyncState).where(ZFinanceSyncState.provider == "z_finance"))
            state.cursor = str(next_cursor) if next_cursor else cursor
            state.last_synced_at = datetime.utcnow()
            state.last_error = None
            db.commit()
            cursor = str(next_cursor) if next_cursor else cursor
    except Exception as exc:
        db.rollback()
        state = db.scalar(select(ZFinanceSyncState).where(ZFinanceSyncState.provider == "z_finance"))
        if state is not None:
            state.last_error = _safe_error(exc)
            db.commit()
        raise
    finally:
        finance_client.close()
    return {
        "accounts_processed": account_count,
        "transactions_processed": transaction_count,
        "payouts_processed": payout_count,
        "cursor": state.cursor,
        "synced_at": state.last_synced_at,
    }


def _unwrap(value):
    while isinstance(value, dict) and isinstance(value.get("data"), (dict, list)):
        value = value["data"]
    return value


def _extract_list(value, key: str) -> list[dict]:
    value = _unwrap(value)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)] if key != "payouts" else []
    if not isinstance(value, dict):
        return []
    result = value.get(key, [])
    return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []


def _parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if not value:
        return datetime.utcnow()
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed


def _upsert_account(db: Session, payload: dict, external_id: str, settings: Settings) -> None:
    account = db.scalar(select(FinancialAccount).where(
        FinancialAccount.provider == "z_finance", FinancialAccount.external_id == external_id
    ))
    if account is None:
        account = FinancialAccount(
            provider="z_finance", external_id=external_id,
            account_type="bank" if external_id == settings.z_finance_operating_account_id else "credit_card",
            name="Operating account" if external_id == settings.z_finance_operating_account_id else "Purchasing card",
        )
        db.add(account)
    balances = payload.get("balances") if isinstance(payload.get("balances"), dict) else payload
    has_balance = any(key in balances for key in ("current", "currentBalance", "available", "availableBalance"))
    account.status = "connected" if has_balance else "stale"
    account.currency = str(payload.get("currency") or balances.get("currency") or "USD")
    account.mask = str(payload.get("mask") or "")[-4:]
    account.last_synced_at = datetime.utcnow()
    if has_balance:
        current = balances.get("current", balances.get("currentBalance"))
        available = balances.get("available", balances.get("availableBalance"))
        if current is not None:
            account.current_balance = float(current)
        account.available_balance = float(available) if available is not None else None
        db.flush()
        db.add(BalanceSnapshot(
            financial_account_id=account.id,
            current_balance=account.current_balance,
            available_balance=account.available_balance,
            captured_at=account.last_synced_at,
        ))


def _signed_amount(payload: dict, classification: str) -> float:
    amount = abs(float(payload.get("amount") or 0))
    direction = str(payload.get("direction") or "").lower()
    if direction in {"outflow", "debit", "expense"}:
        return -amount
    if direction in {"inflow", "credit", "income"}:
        return amount
    return -amount if classification in OUTFLOWS else amount


def _upsert_transaction(db: Session, payload: dict, external_id: str, account_id: str) -> None:
    classification = str(payload.get("autozsType") or payload.get("classification") or "").lower()
    if classification not in CLASSIFICATIONS:
        classification = "unclassified"
    tx = db.scalar(select(ZFinanceTransaction).where(ZFinanceTransaction.external_id == external_id))
    if tx is None:
        tx = ZFinanceTransaction(external_id=external_id, account_external_id=account_id)
        db.add(tx)
    tx.account_external_id = account_id
    tx.classification = classification
    tx.direction = str(payload.get("direction") or "")
    tx.amount = _signed_amount(payload, classification)
    tx.currency = str(payload.get("currency") or "USD")
    tx.pending = bool(payload.get("pending", False))
    tx.occurred_at = _parse_datetime(payload.get("postedAt") or payload.get("date") or payload.get("occurredAt"))
    tx.description = str(payload.get("description") or payload.get("name") or "")[:512]
    tx.supplier_order_ref = _optional_str(payload.get("supplierOrderId") or payload.get("supplier_order_id"))
    nested_payout = payload.get("payout") if isinstance(payload.get("payout"), dict) else {}
    tx.payout_ref = _optional_str(
        payload.get("payoutId") or payload.get("payout_id") or nested_payout.get("id")
    )
    tx.reconciliation_status = "excluded" if classification in EXCLUDED else "needs_review"
    tx.reconciliation_note = "Excluded from P&L by classification." if classification in EXCLUDED else None


def _upsert_payout(db: Session, payload: dict) -> None:
    external_id = str(payload.get("id") or payload.get("payoutId") or "")
    if not external_id:
        return
    payout = db.scalar(select(ZFinancePayout).where(ZFinancePayout.external_id == external_id))
    if payout is None:
        payout = ZFinancePayout(external_id=external_id)
        db.add(payout)
    payout.store_key = normalize_store_key(payload.get("storeKey") or payload.get("account"))
    payout.amount = abs(float(payload.get("amount") or 0))
    payout.currency = str(payload.get("currency") or "USD")
    payout.status = str(payload.get("status") or "expected").lower()
    payout.payout_at = _parse_datetime(payload.get("payoutAt") or payload.get("date"))


def _reconcile(db: Session) -> None:
    supplier_orders = list(db.scalars(select(SupplierOrder).where(
        SupplierOrder.status.in_(["placed", "shipped", "delivered"])
    )).all())
    payouts = list(db.scalars(select(ZFinancePayout)).all())
    txs = list(db.scalars(select(ZFinanceTransaction).where(
        ZFinanceTransaction.reconciliation_status != "excluded"
    )).all())
    for tx in txs:
        tx.matched_supplier_order_id = None
        tx.matched_payout_id = None
        tx.reconciliation_status = "needs_review"
        tx.reconciliation_note = "No deterministic match."
        if tx.classification == "supplier_charge":
            matches = []
            if tx.supplier_order_ref:
                matches = [
                    o for o in supplier_orders
                    if (o.external_order_id == tx.supplier_order_ref or str(o.id) == tx.supplier_order_ref)
                    and _money(o.total) == _money(abs(tx.amount))
                ]
            else:
                matches = [o for o in supplier_orders if _money(o.total) == _money(abs(tx.amount)) and _within_days(o.placed_at or o.created_at, tx.occurred_at, 3)]
            if len(matches) == 1:
                tx.matched_supplier_order_id = matches[0].id
                tx.reconciliation_status = "matched"
                tx.reconciliation_note = "Matched supplier order deterministically."
        elif tx.classification == "payout":
            matches = []
            if tx.payout_ref:
                matches = [
                    p for p in payouts
                    if p.external_id == tx.payout_ref and _money(p.amount) == _money(abs(tx.amount))
                ]
            else:
                matches = [p for p in payouts if _money(p.amount) == _money(abs(tx.amount)) and _within_days(p.payout_at, tx.occurred_at, 3)]
            if len(matches) == 1:
                payout = matches[0]
                tx.matched_payout_id = payout.id
                tx.reconciliation_status = "matched"
                tx.reconciliation_note = "Matched payout deterministically."
                payout.status = "matched"
                payout.matched_transaction_external_id = tx.external_id
        elif tx.classification in {"ebay_fee", "refund", "subscription"}:
            tx.reconciliation_status = "matched"
            tx.reconciliation_note = "Accepted normalized P&L classification."


def build_summary(db: Session, period: str, start_date: date | None, end_date: date | None) -> dict:
    start, end = period_bounds(period, start_date, end_date)
    orders = list(db.scalars(select(Order).options(selectinload(Order.items), selectinload(Order.supplier_orders))).all())
    orders = [o for o in orders if _in_range(o.created_at, start, end) and o.status not in {"cancelled"}]
    supplier_orders = [s for o in orders for s in o.supplier_orders if s.status in {"placed", "shipped", "delivered"}]
    txs = list(db.scalars(select(ZFinanceTransaction).where(ZFinanceTransaction.reconciliation_status == "matched")).all())
    txs = [tx for tx in txs if _in_range(tx.occurred_at, start, end)]
    revenue = sum(float(o.total or 0) for o in orders)
    source_cost = sum(float(s.item_subtotal or 0) + float(s.sales_tax or 0) for s in supplier_orders)
    shipping = sum(float(s.shipping_cost or 0) for s in supplier_orders)
    fees = sum(abs(tx.amount) for tx in txs if tx.classification == "ebay_fee")
    refunds = sum(abs(tx.amount) for tx in txs if tx.classification == "refund")
    subscriptions = sum(abs(tx.amount) for tx in txs if tx.classification == "subscription")
    projected = sum(float(item.expected_profit or 0) for order in orders for item in order.items)
    bank, card = _allowed_accounts(db)
    missing = []
    cash = _balance(bank, prefer_available=True)
    card_balance = _balance(card)
    if cash is None:
        missing.append("operating_account_balance")
    if card_balance is None:
        missing.append("purchasing_card_balance")
    pending_deposits = sum(tx.amount for tx in db.scalars(select(ZFinanceTransaction).where(
        ZFinanceTransaction.classification == "payout", ZFinanceTransaction.pending.is_(True)
    )).all() if tx.amount > 0)
    unmatched = db.query(ZFinanceTransaction).filter(ZFinanceTransaction.reconciliation_status == "needs_review").count()
    return {
        "period": period,
        "start_date": start.date().isoformat() if start else None,
        "end_date": end.date().isoformat() if end else None,
        "store_key": DEFAULT_EBAY_STORE_KEY,
        "sales_revenue": round(revenue, 2),
        "product_source_costs": round(source_cost, 2),
        "source_shipping": round(shipping, 2),
        "ebay_fees": round(fees, 2),
        "refunds": round(refunds, 2),
        "subscriptions": round(subscriptions, 2),
        "realized_net_profit_loss": round(revenue - source_cost - shipping - fees - refunds - subscriptions, 2),
        "projected_profit": round(projected, 2),
        "available_cash": cash,
        "credit_card_balance": card_balance,
        "pending_deposits": round(pending_deposits, 2),
        "unmatched_transaction_count": unmatched,
        "missing_data": missing,
    }


def build_orders(db: Session, period: str, start_date: date | None, end_date: date | None) -> dict:
    start, end = period_bounds(period, start_date, end_date)
    orders = list(db.scalars(select(Order).options(selectinload(Order.items), selectinload(Order.supplier_orders))).all())
    rows = []
    for order in orders:
        if not _in_range(order.created_at, start, end):
            continue
        rows.append({
            "order_id": order.ebay_order_id,
            "store_key": normalize_store_key(order.account_id),
            "status": order.status,
            "ordered_at": order.created_at,
            "sales_revenue": round(float(order.total or 0), 2),
            "projected_profit": round(sum(float(item.expected_profit or 0) for item in order.items), 2),
            "supplier_product_cost": round(sum(float(s.item_subtotal or 0) + float(s.sales_tax or 0) for s in order.supplier_orders), 2),
            "source_shipping": round(sum(float(s.shipping_cost or 0) for s in order.supplier_orders), 2),
            "supplier_order_statuses": sorted({s.status for s in order.supplier_orders}),
        })
    return {"orders": rows, "count": len(rows)}


def build_payouts(db: Session, period: str, start_date: date | None, end_date: date | None) -> dict:
    start, end = period_bounds(period, start_date, end_date)
    rows = [{
        "payout_id": p.external_id,
        "store_key": normalize_store_key(p.store_key),
        "amount": round(float(p.amount), 2),
        "currency": p.currency,
        "status": p.status,
        "payout_at": p.payout_at,
        "matched": bool(p.matched_transaction_external_id),
    } for p in db.scalars(select(ZFinancePayout).order_by(ZFinancePayout.payout_at.desc())).all()
        if _in_range(p.payout_at, start, end)]
    return {"payouts": rows, "count": len(rows)}


def _allowed_accounts(db: Session):
    settings = get_settings()
    accounts = {a.external_id: a for a in db.scalars(select(FinancialAccount).where(FinancialAccount.provider == "z_finance")).all()}
    return accounts.get(settings.z_finance_operating_account_id), accounts.get(settings.z_finance_purchasing_card_id)


def _balance(account: FinancialAccount | None, prefer_available: bool = False) -> float | None:
    if account is None or account.status != "connected":
        return None
    value = account.available_balance if prefer_available and account.available_balance is not None else account.current_balance
    return round(float(value), 2)


def _optional_str(value) -> str | None:
    return str(value) if value not in {None, ""} else None


def _in_range(value: datetime, start: datetime | None, end: datetime | None) -> bool:
    return (start is None or value >= start) and (end is None or value <= end)


def _within_days(a: datetime | None, b: datetime | None, days: int) -> bool:
    return bool(a and b and abs((a - b).total_seconds()) <= days * 86400)


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"Z Finance returned HTTP {exc.response.status_code}."
    return type(exc).__name__

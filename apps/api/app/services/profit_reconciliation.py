"""Read-only eBay order financial observations, reconciled before use in P&L."""
import hashlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse, parse_qs, urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.models.domain import AppSetting, Order, SupplierOrder

PREFIX = "profit_reconciliation:"


def state_for(db, order_id):
    row = db.scalar(select(AppSetting).where(AppSetting.key == PREFIX + str(order_id)))
    try:
        return json.loads(row.value) if row else {}
    except (ValueError, TypeError):
        return {}


def save_state(db, order_id, value):
    key = PREFIX + str(order_id)
    row = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is None:
        row = AppSetting(key=key, value="{}")
        db.add(row)
    row.value = json.dumps(value)


def next_order(db: Session, account_key: str):
    now = datetime.utcnow()
    orders = db.scalars(select(Order).options(selectinload(Order.supplier_orders)).where(
        Order.account_id == account_key, Order.status != "cancelled"
    ).order_by(Order.id.desc())).all()
    for order in orders:
        if account_key == "sandbox" or not (order.status in {"shipped", "delivered", "completed"}
            or any(s.status in {"placed", "shipped", "delivered"} for s in order.supplier_orders)):
            continue
        state = state_for(db, order.id)
        if state.get("next_check_at") and datetime.fromisoformat(state["next_check_at"]) > now:
            continue
        state.update(status="checking", last_attempt_at=now.isoformat(),
                     next_check_at=(now + timedelta(hours=6)).isoformat())
        save_state(db, order.id, state)
        db.commit()
        params = {"mode": "SH", "orderid": order.ebay_order_id, "autozs_profit_order": order.id}
        if order.sales_record_number:
            params["srn"] = order.sales_record_number
        return {"order_id": order.id, "ebay_order_id": order.ebay_order_id, "account_key": account_key,
                "url": "https://www.ebay.com/mesh/ord/details?" + urlencode(params)}
    return None


def parse_financial_text(text: str):
    # Deliberately limited to the actual eBay layout validated on the live order page.
    # Ambiguous refunds/credits or extra cost rows require reconciliation, not guesses.
    normalized = re.sub(r"\s+", " ", text).strip()
    money = r"\$([0-9,]+\.[0-9]{2})"
    pattern = (r"What your buyer paid Subtotal " + money + r" Shipping " + money
               + r" Sales tax\*? " + money + r" Order total\*\*? " + money
               + r" What you earned Order total " + money
               + r" eBay collected from buyer Sales tax -" + money
               + r" Selling costs Transaction fees -" + money
               + r" Order earnings " + money)
    match = re.fullmatch(pattern, normalized)
    if not match:
        raise ValueError("eBay financial breakdown is missing or contains unsupported costs/refunds; review required.")
    subtotal, shipping, tax, total, earned_total, collected_tax, fees, earnings = [Decimal(v.replace(",", "")) for v in match.groups()]
    if subtotal + shipping + tax != total or total != earned_total or tax != collected_tax or subtotal + shipping - fees != earnings:
        raise ValueError("eBay revenue, tax, fees and earnings do not reconcile exactly.")
    return {"subtotal": float(subtotal), "shipping": float(shipping), "tax": float(tax),
            "total": float(total), "fees": float(fees), "earnings": float(earnings)}


def record_observation(db: Session, order_id: int, payload: dict):
    order = db.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order_id))
    if order is None:
        raise ValueError("Order not found.")
    source = str(payload.get("source_url", ""))
    url = urlparse(source)
    if (payload.get("account_key") != order.account_id or payload.get("ebay_order_id") != order.ebay_order_id
        or url.scheme != "https" or url.hostname != "www.ebay.com" or url.path != "/mesh/ord/details"
        or parse_qs(url.query).get("orderid") != [order.ebay_order_id]):
        raise ValueError("Financial observation does not match the eBay order/account.")
    now = datetime.utcnow()
    values = parse_financial_text(str(payload.get("financial_text", "")))
    merchandise = round(sum(float(i.sale_price or 0) * int(i.quantity or 0) for i in order.items), 2)
    if abs(merchandise - values["subtotal"]) > .001:
        raise ValueError("eBay subtotal differs from imported order items; refresh order report.")
    if abs(float(order.total or 0) - values["total"]) > .001:
        raise ValueError("eBay total differs from imported order; refresh order report.")
    evidence = {"source_url": source, "values": values, "observed_at": now.isoformat(),
                "financial_text": payload["financial_text"], "order_id": order.id}
    digest = hashlib.sha256(json.dumps({"order_id":order.id, "values":values},sort_keys=True).encode()).hexdigest()
    key = "profit_evidence:" + digest
    if db.scalar(select(AppSetting).where(AppSetting.key == key)) is None:
        db.add(AppSetting(key=key, value=json.dumps(evidence)))
    order.ebay_fee_amount = values["fees"]
    order.ebay_fee_evidence_ref = key
    order.ebay_fee_recorded_at = now
    order.buyer_shipping_revenue = values["shipping"]
    if payload.get("paid_date"):
        try:
            order.paid_at = datetime.strptime(payload["paid_date"], "%b %d, %Y")
        except ValueError:
            pass
    state = state_for(db, order.id)
    state.update(status="verified", last_verified_at=now.isoformat(), error=None,
                 next_check_at=(now + timedelta(hours=6)).isoformat(), evidence_ref=key)
    save_state(db, order.id, state)
    db.commit()
    return {"status":"verified", "order_id":order.id, **values}


def record_failure(db, order_id, error):
    if db.get(Order, order_id) is None:
        raise ValueError("Order not found.")
    state = state_for(db, order_id)
    state.update(status="needs_review", error=str(error)[:500],
                 next_check_at=(datetime.utcnow()+timedelta(hours=6)).isoformat())
    save_state(db, order_id, state)
    db.commit()
    return {"status":"needs_review", "order_id":order_id}

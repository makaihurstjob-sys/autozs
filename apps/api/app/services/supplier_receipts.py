"""Verify saved supplier costs against read-only Home Depot order receipts."""
import hashlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse, parse_qs, urlencode
from sqlalchemy import select
from app.models.domain import AppSetting, SupplierOrder
from app.services.profit_reconciliation import state_for, save_state


def receipt_state(db, supplier_id):
    return state_for(db, f"supplier:{supplier_id}")


def next_receipt(db):
    now = datetime.utcnow()
    orders = db.scalars(select(SupplierOrder).where(
        SupplierOrder.supplier == "home_depot",
        SupplierOrder.status.in_(["placed", "shipped", "delivered"])
    ).order_by(SupplierOrder.id)).all()
    for order in orders:
        if not order.external_order_id or order.order.account_id == "sandbox":
            continue
        state = receipt_state(db, order.id)
        if state.get("next_check_at") and datetime.fromisoformat(state["next_check_at"]) > now:
            continue
        state.update(status="checking", next_check_at=(now + timedelta(hours=6)).isoformat())
        save_state(db, f"supplier:{order.id}", state)
        db.commit()
        return {"supplier_order_id": order.id, "external_order_id": order.external_order_id,
                "url": "https://www.homedepot.com/myaccount/order-details?" + urlencode({"orderNumber": order.external_order_id})}
    return None


def fail_receipt(db, supplier_id, error):
    state = receipt_state(db, supplier_id)
    state.update(status="needs_review", error=str(error)[:500],
                 next_check_at=(datetime.utcnow() + timedelta(hours=6)).isoformat())
    save_state(db, f"supplier:{supplier_id}", state)
    db.commit()


def parse_receipt(text):
    text = re.sub(r"\s+", " ", str(text)).strip()
    money = r"\$([0-9,]+\.[0-9]{2})"
    match = re.fullmatch(r"Subtotal: " + money + r" Delivery: (FREE|\$[0-9,]+\.[0-9]{2}) Sales Tax: " + money + r" Total: " + money, text)
    if not match:
        raise ValueError("Supplier receipt has missing or unsupported charges; review required.")
    subtotal, delivery, tax, total = match.groups()
    amounts = [Decimal(v.replace("$", "").replace(",", "")) if v != "FREE" else Decimal(0) for v in [subtotal, delivery, tax, total]]
    if sum(amounts[:3]) != amounts[3] or amounts[3] <= 0:
        raise ValueError("Supplier receipt subtotal, delivery and tax do not equal its total.")
    return dict(zip(["item_subtotal", "shipping_cost", "sales_tax", "total"], map(float, amounts)))


def capture_receipt(db, order, payload):
    url = urlparse(str(payload.get("source_url", "")))
    if (url.scheme != "https" or url.hostname != "www.homedepot.com"
        or url.path != "/myaccount/order-details"
        or parse_qs(url.query).get("orderNumber") != [order.external_order_id]
        or payload.get("external_order_id") != order.external_order_id
        or order.supplier != "home_depot"
        or order.status not in {"placed", "shipped", "delivered"}):
        raise ValueError("Supplier receipt does not match the purchased order.")
    values = parse_receipt(payload.get("financial_text", ""))
    now = datetime.utcnow()
    evidence = {"supplier_order_id": order.id, "external_order_id": order.external_order_id,
                "source_url": payload["source_url"], "financial_text": payload["financial_text"],
                "values": values, "observed_at": now.isoformat()}
    key = "supplier_receipt:" + hashlib.sha256(json.dumps({"id":order.id,"values":values},sort_keys=True).encode()).hexdigest()
    if db.scalar(select(AppSetting).where(AppSetting.key == key)) is None:
        db.add(AppSetting(key=key, value=json.dumps(evidence)))
    state = receipt_state(db, order.id)
    mismatch = any(abs(float(getattr(order, field) or 0) - value) > .001 for field,value in values.items())
    state.update(status="needs_review" if mismatch else "verified", evidence_ref=key,
                 observed_values=values, last_observed_at=now.isoformat(),
                 error="Saved supplier costs differ from the actual receipt; payment reconciliation required." if mismatch else None,
                 next_check_at=(now + timedelta(hours=6)).isoformat())
    save_state(db, f"supplier:{order.id}", state)
    db.commit()
    return state

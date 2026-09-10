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
    charge_text = str(payload.get("charge_history_text") or "")
    charge_verified = False
    if charge_text:
        normalized = re.sub(r"\s+", " ", charge_text).strip()
        money = r"\$([0-9,]+\.[0-9]{2})"
        # Only a single observed Mastercard charge with no adjustments/refunds.
        # Other tenders and split payments remain for review, never inferred.
        match = re.fullmatch(r"Charge History CHARGE [A-Z][a-z]+ \d{1,2}, \d{4} \| MA - \d{4} " + money
            + r" Subtotal " + money + r" Delivery FREE Pickup FREE ProXtra Savings FREE Sales Tax \([0-9.]+%\) " + money
            + r" Refund Total " + money + r" Original Total " + money + r" Adjusted Total " + money, normalized)
        if match:
            charge, subtotal, tax, refund, original, adjusted = [Decimal(v.replace(",", "")) for v in match.groups()]
            charge_verified = (charge == original == adjusted == Decimal(str(values["total"]))
                and subtotal == Decimal(str(values["item_subtotal"])) and tax == Decimal(str(values["sales_tax"]))
                and subtotal + tax == charge and refund == 0 and values["shipping_cost"] == 0)
        if not charge_verified:
            raise ValueError("Supplier charge history contains unsupported payments, refunds or adjustments; review required.")
    now = datetime.utcnow()
    evidence = {"supplier_order_id": order.id, "external_order_id": order.external_order_id,
                "source_url": payload["source_url"], "financial_text": payload["financial_text"],
                "values": values, "observed_at": now.isoformat(), "charge_history_text": charge_text,
                "previous_costs": {field: getattr(order, field) for field in values},
                "previous_card_amount": order.card_amount}
    key = "supplier_receipt:" + hashlib.sha256(json.dumps({"id":order.id,"values":values,"charge":charge_text},sort_keys=True).encode()).hexdigest()
    if db.scalar(select(AppSetting).where(AppSetting.key == key)) is None:
        db.add(AppSetting(key=key, value=json.dumps(evidence)))
    state = receipt_state(db, order.id)
    mismatch = any(abs(float(getattr(order, field) or 0) - value) > .001 for field,value in values.items())
    corrected = False
    if charge_verified and not order.gift_card_id and not order.gift_card_amount and order.payment_method == "credit_card":
        corrected = mismatch or abs(float(order.card_amount or 0) - values["total"]) > .001
        for field, value in values.items():
            setattr(order, field, value)
        order.card_amount = values["total"]
        mismatch = False
    state.update(status="needs_review" if mismatch else "verified", evidence_ref=key,
                 observed_values=values, last_observed_at=now.isoformat(), charge_verified=charge_verified,
                 payment_corrected=corrected or state.get("payment_corrected", False),
                 error="Saved supplier costs differ from the actual receipt; payment reconciliation required." if mismatch else None,
                 next_check_at=(now + timedelta(hours=6)).isoformat())
    save_state(db, f"supplier:{order.id}", state)
    db.commit()
    return state

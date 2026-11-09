"""Versioned purchase approvals. No buyer or payment secrets in the audit ledger."""
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import secrets
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.models.domain import AppSetting, SupplierOrder
from app.services.purchase_policy import cents


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def snapshot(row):
    order = row.order
    if order is None or not order.ebay_order_id or not order.account_id:
        raise ValueError("Exact eBay sale identity is required")
    if row.supplier != "home_depot" or len(row.items) != 1 or row.gift_card_id:
        raise ValueError("Saved Privacy checkout supports one Home Depot item; other suppliers need an adapter")
    items = []
    for item in sorted(row.items, key=lambda i: i.id):
        url = urlsplit(item.source_url)
        if url.scheme != "https" or url.netloc != "www.homedepot.com" or not url.path.startswith("/p/"):
            raise ValueError("An exact Home Depot product URL is required")
        if type(item.quantity) is not int or item.quantity <= 0:
            raise ValueError("A positive supplier quantity is required")
        items.append(dict(id=item.id, order_item_id=item.order_item_id, product_id=item.product_id,
            title=item.title, source_url=item.source_url, quantity=item.quantity,
            unit_price_cents=cents(item.unit_price, "Unit price")))
    subtotal = sum(i["quantity"] * i["unit_price_cents"] for i in items)
    shipping, tax, total = (cents(v, n) for v, n in ((row.shipping_cost, "Shipping"),
        (row.sales_tax, "Tax"), (row.total, "Total")))
    if subtotal <= 0 or total != subtotal + shipping + tax or cents(row.item_subtotal, "Subtotal") != subtotal:
        raise ValueError("Supplier plan must include consistent item, shipping, tax and total costs")
    # Bind destination changes without storing recipient data in the approval ledger.
    destination = [getattr(row, key) for key in ("recipient_name", "address_line1", "address_line2",
        "city", "state", "postal_code", "phone")]
    return dict(version=1, supplier_order_id=row.id, order_id=row.order_id,
        ebay_order_id=order.ebay_order_id, account_key=order.account_id, supplier=row.supplier,
        payment_policy="saved_privacy_only", currency="USD", items=items,
        item_subtotal_cents=subtotal, shipping_cents=shipping, tax_cents=tax, total_cents=total,
        destination_digest=_hash(destination))


def review(row):
    value = snapshot(row)
    fingerprint = _hash(value)
    value.pop("destination_digest")
    return {"snapshot": value, "fingerprint": fingerprint,
        "notice": "One purchase only. Changed item or price requires fresh approval. Saved Privacy payment only."}


def _setting(db, key):
    return db.scalar(select(AppSetting).where(AppSetting.key == key))


def record_approval(db, row, fingerprint):
    value = snapshot(row)
    if not hmac.compare_digest(_hash(value), fingerprint):
        raise ValueError("Purchase plan changed. Refresh and approve the new item and price")
    approval_id = secrets.token_hex(16)
    now = datetime.utcnow()
    value.update(approval_id=approval_id, fingerprint=fingerprint, approved_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=30)).isoformat())
    # Append-only version; the pointer is the sole mutable lookup.
    db.add(AppSetting(key=f"purchase_approval:{row.id}:{approval_id}", value=json.dumps(value)))
    pointer = _setting(db, f"purchase_approval_current:{row.id}")
    if pointer is None:
        db.add(AppSetting(key=f"purchase_approval_current:{row.id}", value=approval_id))
    else:
        pointer.value = approval_id
    audit(db, row.id, "approved", approval_id=approval_id)
    return value


def require_approval(db, row):
    pointer = _setting(db, f"purchase_approval_current:{row.id}")
    entry = _setting(db, f"purchase_approval:{row.id}:{pointer.value}") if pointer else None
    if entry is None:
        raise ValueError("Use Place Order after reviewing the exact purchase plan on the dashboard")
    value = json.loads(entry.value)
    if datetime.fromisoformat(value["expires_at"]) <= datetime.utcnow():
        raise ValueError("Purchase approval expired. Refresh and approve again")
    if not hmac.compare_digest(value["fingerprint"], _hash(snapshot(row))):
        raise ValueError("Approved purchase changed. Refresh and approve the new item and price")
    if not row.approved_at or row.approved_at.isoformat() != value["approved_at"]:
        raise ValueError("Purchase approval version does not match this checkout")
    return value


def audit(db, supplier_order_id, event, **safe_fields):
    # Callers pass machine events/identifiers, never page text, address or credentials.
    db.add(AppSetting(key=f"purchase_audit:{supplier_order_id}:{secrets.token_hex(16)}",
        value=json.dumps(dict(event=event, at=datetime.utcnow().isoformat(), **safe_fields))))


def history(db, supplier_order_id):
    rows = db.scalars(select(AppSetting).where(
        AppSetting.key.startswith(f"purchase_audit:{supplier_order_id}:"))).all()
    return sorted((json.loads(r.value) for r in rows), key=lambda v: v["at"])

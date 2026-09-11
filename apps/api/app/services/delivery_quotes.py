"""Cart observations are regional evidence, never a nationwide shipping promise."""
from datetime import datetime, timedelta
import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import SupplierDeliveryQuote, SupplierProduct


def home_depot_item_id(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc != "www.homedepot.com":
        return None
    match = re.fullmatch(r"/p/[^/]+/(\d+)/?", parsed.path)
    return match[1] if match else None


def record_cart_quote(db: Session, source_url: str, postal_code: str, quantity: int, delivery_charge: float) -> int:
    item_id = home_depot_item_id(source_url)
    if not item_id:
        raise ValueError("Expected a Home Depot product URL")
    suppliers = [s for s in db.scalars(select(SupplierProduct)).all()
                 if home_depot_item_id(s.source_url) == item_id]
    if not suppliers:
        raise ValueError("Cart product is not in the AutoZS catalog")
    for supplier in suppliers:
        quote = db.scalar(select(SupplierDeliveryQuote).where(
            SupplierDeliveryQuote.supplier_product_id == supplier.id,
            SupplierDeliveryQuote.postal_code == postal_code,
            SupplierDeliveryQuote.quantity == quantity,
        ))
        if quote is None:
            quote = SupplierDeliveryQuote(supplier_product_id=supplier.id, postal_code=postal_code, quantity=quantity)
            db.add(quote)
        quote.delivery_charge = delivery_charge
        quote.observed_at = datetime.utcnow()
    db.commit()
    return len(suppliers)


def delivery_risk_reason(db: Session, product_id: int, *, include_coverage: bool = True) -> str | None:
    # Paid observations remain blocking when old: age is not evidence that a fee disappeared.
    quote = db.scalar(select(SupplierDeliveryQuote).join(SupplierProduct).where(
        SupplierProduct.product_id == product_id,
        SupplierDeliveryQuote.delivery_charge > 0,
    ).order_by(SupplierDeliveryQuote.observed_at.desc()))
    if quote:
        return (f"Supplier cart delivery costs ${quote.delivery_charge:.2f} to ZIP {quote.postal_code} "
                f"for quantity {quote.quantity}; recheck that destination before listing.")
    if include_coverage:
        from app.services.delivery_checks import coverage_reason
        return coverage_reason(db, product_id)
    return None


def product_delivery_quotes(db: Session, product_id: int) -> dict:
    rows = db.scalars(select(SupplierDeliveryQuote).join(SupplierProduct).where(
        SupplierProduct.product_id == product_id,
    ).order_by(SupplierDeliveryQuote.postal_code)).all()
    cutoff = datetime.utcnow() - timedelta(hours=24)
    return {"product_id": product_id, "blocking_reason": delivery_risk_reason(db, product_id),
            "nationwide_free_shipping_verified": False,
            "quotes": [{"postal_code": q.postal_code, "quantity": q.quantity,
                        "delivery_charge": q.delivery_charge, "observed_at": q.observed_at,
                        "stale": q.observed_at < cutoff} for q in rows]}

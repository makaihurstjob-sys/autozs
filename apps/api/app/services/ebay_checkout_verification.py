"""Fail-closed checkout gate for observations from the local signed-in browser worker."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qs
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.domain import SupplierOrder, EbayCheckoutVerification


class VerificationObservation(BaseModel):
    ebay_order_id: str
    account_key: str
    source_url: str
    status: Literal["eligible", "cancelled", "refunded", "fulfilled", "unknown"]
    observed_at: datetime
    evidence: str = Field(min_length=1, max_length=12000)


def context(row: SupplierOrder) -> dict:
    if (row.status not in {"queued", "placing"} or row.external_order_id or row.placed_at
            or row.order is None or row.order.status in {"cancelled", "shipped", "delivered", "refunded"}):
        raise ValueError("Checkout is not eligible for live verification; reconcile the order.")
    if not row.order.ebay_order_id or not row.order.account_id:
        raise ValueError("Exact eBay order and account identity are required.")
    return {"supplier_order_id": row.id, "ebay_order_id": row.order.ebay_order_id,
            "account_key": row.order.account_id}


def next_context(db: Session):
    for row in db.scalars(select(SupplierOrder).where(SupplierOrder.status == "queued")
                          .order_by(SupplierOrder.approved_at, SupplierOrder.id)):
        try:
            return context(row)
        except ValueError:
            continue
    return None


def record(db: Session, row: SupplierOrder, observation: VerificationObservation):
    identity = context(row)
    if observation.ebay_order_id != identity["ebay_order_id"] or observation.account_key != identity["account_key"]:
        raise ValueError("Live eBay evidence must match the exact order and account.")
    url = urlsplit(observation.source_url)
    if (url.scheme != "https" or url.netloc != "www.ebay.com" or url.path != "/mesh/ord/details"
            or parse_qs(url.query).get("orderid") != [identity["ebay_order_id"]]):
        raise ValueError("Evidence must come from the exact eBay Seller Hub order detail URL.")
    if observation.observed_at.tzinfo is None:
        raise ValueError("Observation timestamp must include a timezone.")
    now = datetime.utcnow()
    observed = observation.observed_at.astimezone(timezone.utc).replace(tzinfo=None)
    if not 0 <= (now - observed).total_seconds() <= 60:
        raise ValueError("Live eBay observation is stale or in the future.")
    if not observation.evidence.strip():
        raise ValueError("Actual eBay status evidence is required.")
    terminal = db.scalar(select(EbayCheckoutVerification.id).where(
        EbayCheckoutVerification.supplier_order_id == row.id,
        EbayCheckoutVerification.status.in_(["cancelled", "refunded", "fulfilled"])))
    if terminal is not None and observation.status == "eligible":
        raise ValueError("Prior terminal eBay evidence requires reconciliation; checkout remains held.")
    evidence = EbayCheckoutVerification(supplier_order_id=row.id, **observation.model_dump(exclude={"observed_at"}),
                                        observed_at=observed, verified_at=now)
    db.add(evidence)
    # Negative results never imply that the supplier cancelled or refunded a purchase.
    # Hold the checkout and invalidate its lease, retaining the complete audit observation.
    if observation.status != "eligible":
        row.status = "needs_review"
        row.failure_reason = "Live eBay verification held checkout: " + observation.status
        row.checkout_token = ""
        row.lease_expires_at = None
    db.commit()
    return {"status": evidence.status, "verified_at": now.replace(tzinfo=timezone.utc),
            "expires_at": (observed + timedelta(minutes=2)).replace(tzinfo=timezone.utc)}


def require_fresh(db: Session, row: SupplierOrder):
    identity = context(row)
    latest = db.scalar(select(EbayCheckoutVerification).where(EbayCheckoutVerification.supplier_order_id == row.id)
                       .order_by(EbayCheckoutVerification.id.desc()))
    now = datetime.utcnow()
    if (latest is None or latest.status != "eligible" or latest.ebay_order_id != identity["ebay_order_id"]
            or latest.account_key != identity["account_key"]
            or latest.verified_at < (row.approved_at or datetime.min)
            or not 0 <= (now - latest.observed_at).total_seconds() < 120):
        raise ValueError("Fresh eligible live eBay order evidence is required before checkout.")

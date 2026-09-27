"""Durable product exclusions shared by readiness and unattended listing paths."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import EbayListing, ListingJob, Product


def listing_exclusion_reason(db: Session, product_id: int, *, for_stock_restoration: bool = False) -> str | None:
    product = db.get(Product, product_id)
    if product is not None and product.status == "paused":
        return "Listing excluded: product is intentionally paused"
    if db.scalar(select(EbayListing.id).where(
        EbayListing.product_id == product_id, EbayListing.relist_blocked.is_(True)
    ).limit(1)) is not None:
        return "Listing excluded: relisting is blocked for this product"
    latest = db.scalar(select(ListingJob).where(
        ListingJob.product_id == product_id
    ).order_by(ListingJob.created_at.desc(), ListingJob.id.desc()).limit(1))
    if latest is not None and latest.status == "cancelled":
        # Scope is explicit state, never inferred from human-readable messages.
        if for_stock_restoration and latest.cancellation_scope == "publication_only":
            return None
        return f"Listing excluded: {latest.message or 'latest listing job was cancelled'}"
    return None

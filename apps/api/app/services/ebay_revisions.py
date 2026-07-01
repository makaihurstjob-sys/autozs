from datetime import datetime
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import (
    EbayListing,
    EbayRevisionJob,
    EbayRevisionJobStatus,
    ListingDraft,
    Product,
    ProductStatus,
)
from app.services.ebay_browser_account import assert_ebay_browser_account_can_list


ACTIVE_STATUSES = {
    EbayRevisionJobStatus.queued.value,
    EbayRevisionJobStatus.running.value,
    EbayRevisionJobStatus.paused.value,
}
REVISION_LISTING_STATUSES = {"scheduled", "listed", "live", "active"}


def enqueue_ebay_price_revisions(
    db: Session,
    product_ids: list[int] | None = None,
) -> tuple[int, int]:
    stmt = (
        select(EbayListing, ListingDraft)
        .join(Product, Product.id == EbayListing.product_id)
        .join(ListingDraft, ListingDraft.product_id == Product.id)
        .where(Product.status != ProductStatus.deleted.value)
        .where(EbayListing.status.in_(REVISION_LISTING_STATUSES))
        .where(ListingDraft.marketplace == "ebay")
        .order_by(EbayListing.created_at.desc(), EbayListing.id.desc())
    )
    if product_ids is not None:
        stmt = stmt.where(EbayListing.product_id.in_(set(product_ids)))

    queued = 0
    updated = 0
    seen_listing_ids: set[int] = set()
    for listing, draft in db.execute(stmt).all():
        if listing.id in seen_listing_ids or draft.calculated_price is None:
            continue
        seen_listing_ids.add(listing.id)
        target_price = round(float(draft.calculated_price), 2)
        current_price = round(float(listing.price), 2) if listing.price is not None else None
        active_job = db.scalar(
            select(EbayRevisionJob)
            .where(EbayRevisionJob.ebay_listing_id == listing.id)
            .where(EbayRevisionJob.status.in_(ACTIVE_STATUSES))
            .order_by(EbayRevisionJob.created_at.desc(), EbayRevisionJob.id.desc())
        )
        if current_price == target_price:
            if active_job is not None and active_job.status != EbayRevisionJobStatus.running.value:
                active_job.status = EbayRevisionJobStatus.cancelled.value
                active_job.completed_at = _now()
                active_job.message = "Cancelled because the eBay price already matches the current draft price."
            continue
        if active_job is not None:
            active_job.target_price = target_price
            active_job.old_price = listing.price
            if active_job.status == EbayRevisionJobStatus.paused.value:
                active_job.status = EbayRevisionJobStatus.queued.value
            active_job.message = f"Target price updated to ${target_price:.2f} after pricing settings changed."
            updated += 1
            continue
        db.add(
            EbayRevisionJob(
                product_id=listing.product_id,
                ebay_listing_id=listing.id,
                ebay_account_key=listing.account_id or "manual",
                old_price=listing.price,
                target_price=target_price,
                message=f"Queued eBay price update from {_price(listing.price)} to ${target_price:.2f}.",
            )
        )
        queued += 1
    db.commit()
    return queued, updated


def list_ebay_revision_jobs(
    db: Session,
    status: str | None = None,
    limit: int = 100,
) -> list[EbayRevisionJob]:
    stmt = select(EbayRevisionJob)
    if status:
        stmt = stmt.where(EbayRevisionJob.status == status)
    stmt = stmt.order_by(EbayRevisionJob.created_at.desc(), EbayRevisionJob.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def start_next_ebay_revision_job(db: Session) -> EbayRevisionJob | None:
    running = db.scalar(
        select(EbayRevisionJob)
        .where(EbayRevisionJob.status == EbayRevisionJobStatus.running.value)
        .order_by(EbayRevisionJob.started_at.asc(), EbayRevisionJob.id.asc())
    )
    if running is not None:
        return running
    job = db.scalar(
        select(EbayRevisionJob)
        .where(EbayRevisionJob.status == EbayRevisionJobStatus.queued.value)
        .order_by(EbayRevisionJob.created_at.asc(), EbayRevisionJob.id.asc())
    )
    if job is None:
        return None
    try:
        assert_ebay_browser_account_can_list(db, job.ebay_account_key)
    except ValueError as exc:
        job.status = EbayRevisionJobStatus.paused.value
        job.message = str(exc)
        db.commit()
        db.refresh(job)
        return job
    job.status = EbayRevisionJobStatus.running.value
    job.started_at = _now()
    job.completed_at = None
    job.attempts += 1
    job.message = f"Reserved for eBay price revision to ${job.target_price:.2f}."
    db.commit()
    db.refresh(job)
    return job


def update_ebay_revision_job(
    db: Session,
    job: EbayRevisionJob,
    status: str | None = None,
    message: str | None = None,
) -> EbayRevisionJob:
    if status is not None:
        job.status = status
        if status in {
            EbayRevisionJobStatus.completed.value,
            EbayRevisionJobStatus.failed.value,
            EbayRevisionJobStatus.cancelled.value,
        }:
            job.completed_at = _now()
        if status == EbayRevisionJobStatus.queued.value:
            job.started_at = None
            job.completed_at = None
        if status == EbayRevisionJobStatus.completed.value:
            listing = db.get(EbayListing, job.ebay_listing_id)
            if listing is not None:
                listing.price = job.target_price
    if message is not None:
        job.message = message
    db.commit()
    db.refresh(job)
    return job


def serialize_ebay_revision_job(db: Session, job: EbayRevisionJob) -> dict:
    listing = db.get(EbayListing, job.ebay_listing_id)
    product = db.get(Product, job.product_id)
    listing_id = listing.listing_id if listing is not None else ""
    return {
        "id": job.id,
        "product_id": job.product_id,
        "ebay_listing_id": job.ebay_listing_id,
        "listing_id": listing_id,
        "title": product.title if product is not None else "Missing product",
        "ebay_account_key": job.ebay_account_key,
        "action": job.action,
        "status": job.status,
        "old_price": job.old_price,
        "target_price": job.target_price,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "attempts": job.attempts,
        "message": job.message,
        "assistant_url": _assistant_url(job, listing_id),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _assistant_url(job: EbayRevisionJob, listing_id: str) -> str:
    params = {
        "mode": "ReviseItem",
        "itemId": listing_id,
        "autozs_fill": "1",
        "autozs_product_id": str(job.product_id),
        "autozs_revision_job_id": str(job.id),
        "autozs_workflow": "revise_price",
        "autozs_target_price": f"{job.target_price:.2f}",
        "autozs_account_key": job.ebay_account_key or "manual",
    }
    return f"https://www.ebay.com/sl/list?{urlencode(params)}"


def _now() -> datetime:
    return datetime.utcnow()


def _price(value: float | None) -> str:
    return "the unknown stored price" if value is None else f"${value:.2f}"

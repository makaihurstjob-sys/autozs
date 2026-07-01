from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.domain import EbayListing, ListingJob, ListingJobStatus, Product, ProductStatus
from app.services.ebay_browser_account import assert_ebay_browser_account_can_list
from app.services.importer import build_ebay_listing_package, build_listing_readiness
from app.services.settings import read_pricing_settings


TERMINAL_STATUSES = {
    ListingJobStatus.saved_draft.value,
    ListingJobStatus.completed.value,
    ListingJobStatus.tombstoned.value,
    ListingJobStatus.failed.value,
    ListingJobStatus.cancelled.value,
}


def enqueue_listing_jobs(
    db: Session,
    product_ids: list[int],
    ebay_account_key: str = "manual",
    action: str = "create_draft",
    scheduled_for: datetime | None = None,
    listing_schedule_at: datetime | None = None,
) -> list[ListingJob]:
    scheduled_for = _naive_utc(scheduled_for)
    requested_listing_schedule_at = _naive_utc(listing_schedule_at)
    default_listing_schedule_at = _default_listing_schedule(db)
    jobs: list[ListingJob] = []
    seen: set[int] = set()
    for product_id in product_ids:
        if product_id in seen:
            continue
        seen.add(product_id)
        product = db.get(Product, product_id)
        if product is None or product.status == ProductStatus.deleted.value:
            continue
        product_listing_schedule_at = (
            requested_listing_schedule_at
            or _naive_utc(product.listing_schedule_at)
            or default_listing_schedule_at
        )
        job = db.scalar(
            select(ListingJob)
            .where(ListingJob.product_id == product_id)
            .where(ListingJob.ebay_account_key == ebay_account_key)
            .where(ListingJob.action == action)
            .where(ListingJob.status.not_in(TERMINAL_STATUSES))
            .order_by(ListingJob.created_at.desc(), ListingJob.id.desc())
        )
        if job is None:
            job = ListingJob(
                product_id=product_id,
                ebay_account_key=ebay_account_key,
                action=action,
                scheduled_for=scheduled_for,
                listing_schedule_at=product_listing_schedule_at,
                status=ListingJobStatus.queued.value,
                message="Queued for scheduled publishing" if action == "publish" else "Queued for draft creation",
            )
            db.add(job)
        else:
            job.scheduled_for = scheduled_for
            job.listing_schedule_at = product_listing_schedule_at
            job.status = ListingJobStatus.queued.value if job.status == ListingJobStatus.paused.value else job.status
            job.message = "Scheduled publishing queue updated" if action == "publish" else "Queue schedule updated"
        jobs.append(job)
    db.commit()
    for job in jobs:
        db.refresh(job)
    return jobs


def list_listing_jobs(db: Session, status: str | None = None, limit: int = 100) -> list[ListingJob]:
    stmt = select(ListingJob).order_by(ListingJob.created_at.desc(), ListingJob.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(ListingJob.status == status)
    return list(db.scalars(stmt).all())


def read_listing_job(db: Session, job_id: int) -> ListingJob | None:
    return db.get(ListingJob, job_id)


def start_listing_job(db: Session, job: ListingJob) -> ListingJob:
    try:
        assert_ebay_browser_account_can_list(db, job.ebay_account_key)
    except ValueError as exc:
        job.status = ListingJobStatus.needs_review.value
        job.message = str(exc)
        db.commit()
        db.refresh(job)
        return job
    package = build_ebay_listing_package(db, job.product_id)
    readiness = build_listing_readiness(db, job.product_id)
    if package is None or readiness is None:
        job.status = ListingJobStatus.failed.value
        job.completed_at = _now_utc_naive()
        job.message = "Product was not found or no longer has an eBay package"
    elif not readiness["manual_ready"]:
        job.status = ListingJobStatus.needs_review.value
        job.message = f"Needs review before draft: {', '.join(readiness['missing_manual'])}"
    else:
        job.status = ListingJobStatus.running.value
        job.started_at = _now_utc_naive()
        job.completed_at = None
        job.attempts += 1
        job.message = "Reserved for scheduled eBay publishing" if job.action == "publish" else "Reserved for eBay draft creation"
    db.commit()
    db.refresh(job)
    return job


def start_next_listing_job(
    db: Session,
    ebay_account_key: str | None = None,
    now: datetime | None = None,
) -> ListingJob | None:
    now = _naive_utc(now) or _now_utc_naive()
    stmt = (
        select(ListingJob)
        .where(ListingJob.status == ListingJobStatus.queued.value)
        .where(or_(ListingJob.scheduled_for.is_(None), ListingJob.scheduled_for <= now))
        .order_by(ListingJob.scheduled_for.asc().nullsfirst(), ListingJob.created_at.asc(), ListingJob.id.asc())
    )
    if ebay_account_key:
        stmt = stmt.where(ListingJob.ebay_account_key == ebay_account_key)
    job = db.scalar(stmt)
    if job is None:
        return None
    return start_listing_job(db, job)


def update_listing_job(
    db: Session,
    job: ListingJob,
    status: str | None = None,
    scheduled_for: datetime | None = None,
    listing_schedule_at: datetime | None = None,
    ebay_draft_id: str | None = None,
    listing_id: str | None = None,
    message: str | None = None,
) -> ListingJob:
    scheduled_for = _naive_utc(scheduled_for)
    listing_schedule_at = _naive_utc(listing_schedule_at)
    if status is not None:
        job.status = status
        if status in {
            ListingJobStatus.saved_draft.value,
            ListingJobStatus.completed.value,
            ListingJobStatus.tombstoned.value,
            ListingJobStatus.failed.value,
            ListingJobStatus.cancelled.value,
        }:
            job.completed_at = _now_utc_naive()
        if status == ListingJobStatus.queued.value:
            job.started_at = None
            job.completed_at = None
    if scheduled_for is not None:
        job.scheduled_for = scheduled_for
    if listing_schedule_at is not None:
        job.listing_schedule_at = listing_schedule_at
    if ebay_draft_id is not None:
        job.ebay_draft_id = ebay_draft_id
    if message is not None:
        job.message = message
    if listing_id:
        _upsert_listing_from_completed_job(db, job, listing_id)
    db.commit()
    db.refresh(job)
    return job


def verify_listing_job_draft(
    db: Session,
    job: ListingJob,
    exists: bool,
    ebay_draft_id: str | None = None,
    url: str | None = None,
    message: str | None = None,
) -> ListingJob:
    if ebay_draft_id is not None:
        job.ebay_draft_id = ebay_draft_id
    draft_label = job.ebay_draft_id or ebay_draft_id or "unknown"
    if exists:
        if job.status == ListingJobStatus.tombstoned.value:
            job.status = ListingJobStatus.saved_draft.value
        elif job.status in {ListingJobStatus.running.value, ListingJobStatus.ready_to_save.value, ListingJobStatus.needs_review.value}:
            job.status = ListingJobStatus.saved_draft.value
        job.completed_at = _now_utc_naive()
        job.message = message or f"Verified eBay draft {draft_label} still exists."
    else:
        job.status = ListingJobStatus.tombstoned.value
        job.completed_at = _now_utc_naive()
        detail = message or f"eBay draft {draft_label} was not found. The local eBay record was tombstoned."
        job.message = f"{detail} Checked URL: {url}" if url else detail
        _tombstone_missing_draft_records(db, job)
    db.commit()
    db.refresh(job)
    return job


def serialize_listing_job(db: Session, job: ListingJob) -> dict:
    package = build_ebay_listing_package(db, job.product_id)
    readiness = build_listing_readiness(db, job.product_id)
    if package is None or readiness is None:
        return {
            "id": job.id,
            "product_id": job.product_id,
            "sku": "missing",
            "title": "Missing product",
            "price": None,
            "estimated_profit": None,
            "meets_minimum_profit": None,
            "ebay_account_key": job.ebay_account_key,
            "action": job.action,
            "status": job.status,
            "scheduled_for": job.scheduled_for,
            "listing_schedule_at": job.listing_schedule_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "attempts": job.attempts,
            "ebay_draft_id": job.ebay_draft_id,
            "message": job.message,
            "manual_ready": False,
            "api_ready": False,
            "missing_manual": ["product"],
            "missing_api": ["product"],
            "warnings": ["Product is missing"],
            "image_count": 0,
            "local_image_count": 0,
            "image_upload_status": "missing",
            "source_url": None,
            "assistant_url": _assistant_url(job.product_id, job.id, job.listing_schedule_at, job.ebay_account_key, job.action),
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
    return {
        "id": job.id,
        "product_id": job.product_id,
        "sku": package["sku"],
        "title": package["title"],
        "price": package["price"],
        "estimated_profit": package["estimated_profit"],
        "meets_minimum_profit": package["meets_minimum_profit"],
        "ebay_account_key": job.ebay_account_key,
        "action": job.action,
        "status": job.status,
        "scheduled_for": job.scheduled_for,
        "listing_schedule_at": job.listing_schedule_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "attempts": job.attempts,
        "ebay_draft_id": job.ebay_draft_id,
        "message": job.message,
        "manual_ready": readiness["manual_ready"],
        "api_ready": readiness["api_ready"],
        "missing_manual": readiness["missing_manual"],
        "missing_api": readiness["missing_api"],
        "warnings": readiness["warnings"],
        "image_count": len(package["image_urls"]),
        "local_image_count": len(package["local_image_paths"]),
        "image_upload_status": package["image_upload_status"],
        "source_url": package["source_url"],
        "assistant_url": _assistant_url(job.product_id, job.id, job.listing_schedule_at, job.ebay_account_key, job.action),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _assistant_url(
    product_id: int,
    job_id: int | None = None,
    listing_schedule_at: datetime | None = None,
    ebay_account_key: str = "manual",
    action: str = "create_draft",
) -> str:
    params = {
        "autozs_fill": "1",
        "autozs_product_id": str(product_id),
        "autozs_workflow": "create_draft",
        "autozs_autosave": "1",
        "autozs_account_key": ebay_account_key or "manual",
    }
    if job_id is not None:
        params["autozs_job_id"] = str(job_id)
    if listing_schedule_at is not None:
        params["autozs_listing_schedule_at"] = listing_schedule_at.isoformat()
    if action == "publish" and listing_schedule_at is not None:
        params["autozs_autosubmit"] = "1"
    query = urlencode(params)
    return f"https://www.ebay.com/sl/prelist/home?{query}#{query}"


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _upsert_listing_from_completed_job(db: Session, job: ListingJob, listing_id: str) -> None:
    clean_listing_id = str(listing_id).strip()[:128]
    if not clean_listing_id:
        return
    package = build_ebay_listing_package(db, job.product_id)
    now = _now_utc_naive()
    start = _naive_utc(job.listing_schedule_at) or now
    is_live = start <= now
    listing = db.scalar(
        select(EbayListing).where(
            EbayListing.account_id == job.ebay_account_key,
            EbayListing.listing_id == clean_listing_id,
        )
    )
    if listing is None:
        listing = EbayListing(product_id=job.product_id, listing_id=clean_listing_id, account_id=job.ebay_account_key)
        db.add(listing)
    listing.product_id = job.product_id
    listing.environment = "manual"
    listing.price = package["price"] if package else listing.price
    listing.quantity = max(1, int(listing.quantity or 1))
    listing.status = "active" if is_live else "scheduled"
    listing.started_at = start if is_live else None
    listing.renews_at = (start + timedelta(days=30)) if is_live and listing.renews_at is None else listing.renews_at


def _tombstone_missing_draft_records(db: Session, job: ListingJob) -> None:
    product = db.get(Product, job.product_id)
    # Keep this scoped to draft/scheduled local records. Live active listings are reconciled by the
    # Seller Hub active-listings report, not by draft verification.
    listings = db.scalars(
        select(EbayListing)
        .where(EbayListing.product_id == job.product_id)
        .where(EbayListing.account_id == job.ebay_account_key)
        .where(EbayListing.status.in_(("draft", "scheduled")))
    ).all()
    for listing in listings:
        listing.status = "tombstoned"
    if product is None:
        return
    for listing_draft in product.listing_drafts:
        if listing_draft.marketplace == "ebay":
            listing_draft.status = "tombstoned"


def _default_queue_schedule(db: Session) -> datetime | None:
    settings = read_pricing_settings(db)
    if str(settings.get("default_listing_schedule_mode", "now")) != "scheduled":
        return None
    days_ahead = int(float(settings.get("default_listing_schedule_days_ahead", 0)))
    time_value = str(settings.get("default_listing_schedule_time", "09:00"))
    try:
        hour, minute = [int(part) for part in time_value.split(":")]
    except ValueError:
        hour, minute = 9, 0
    scheduled = _now_utc_naive() + timedelta(days=days_ahead)
    scheduled = scheduled.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled <= _now_utc_naive():
        scheduled = scheduled + timedelta(days=1)
    return scheduled


def _default_listing_schedule(db: Session) -> datetime | None:
    settings = read_pricing_settings(db)
    if str(settings.get("default_listing_schedule_mode", "now")) != "scheduled":
        return None
    days_ahead = int(float(settings.get("default_listing_schedule_days_ahead", 0)))
    time_value = str(settings.get("default_listing_schedule_time", "09:00"))
    try:
        hour, minute = [int(part) for part in time_value.split(":")]
    except ValueError:
        hour, minute = 9, 0
    scheduled = _now_utc_naive() + timedelta(days=days_ahead)
    scheduled = scheduled.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled <= _now_utc_naive():
        scheduled = scheduled + timedelta(days=1)
    return scheduled

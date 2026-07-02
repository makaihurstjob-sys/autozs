from datetime import datetime, timedelta
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
    SupplierProduct,
)
from app.services.ebay_browser_account import assert_ebay_browser_account_can_list
from app.services.importer import calculate_profit
from app.services.settings import read_pricing_settings


ACTIVE_STATUSES = {
    EbayRevisionJobStatus.needs_review.value,
    EbayRevisionJobStatus.queued.value,
    EbayRevisionJobStatus.running.value,
    EbayRevisionJobStatus.paused.value,
}
REVISION_LISTING_STATUSES = {"scheduled", "listed", "live", "active"}
REVISION_LEASE_MINUTES = 15
MAX_REVISION_ATTEMPTS = 3


def _revision_evidence(db: Session, product_id: int, target_price: float, old_price: float | None) -> dict:
    supplier = db.scalar(
        select(SupplierProduct)
        .where(SupplierProduct.product_id == product_id)
        .order_by(SupplierProduct.created_at.asc(), SupplierProduct.id.asc())
    )
    settings = read_pricing_settings(db)
    source_price = supplier.last_price if supplier is not None else None
    source_shipping = supplier.last_shipping if supplier is not None else 0.0
    projected_profit = calculate_profit(target_price, source_price, source_shipping, settings)["profit"]
    minimum_profit = float(settings.get("default_min_profit", 0.0) or 0.0)
    guard_enabled = bool(settings.get("default_min_profit_guard_enabled", False))
    max_change = float(settings.get("ebay_revision_max_change_percent", 25.0) or 25.0)
    change_percent = (
        abs(target_price - old_price) / old_price * 100
        if old_price is not None and old_price > 0
        else None
    )
    reasons: list[str] = []
    guard_passed = True
    if source_price is None:
        guard_passed = False
        reasons.append("Supplier price is missing")
    if source_shipping is None or source_shipping < 0:
        guard_passed = False
        reasons.append("Supplier shipping is unknown")
    if projected_profit is None:
        guard_passed = False
        reasons.append("Projected profit could not be calculated")
    elif guard_enabled and projected_profit < minimum_profit:
        guard_passed = False
        reasons.append(f"Projected profit ${projected_profit:.2f} is below the ${minimum_profit:.2f} minimum")
    if target_price <= 0:
        guard_passed = False
        reasons.append("Target price must be positive")
    exceeds_auto_limit = change_percent is not None and change_percent > max_change
    if exceeds_auto_limit:
        reasons.append(f"Price change {change_percent:.1f}% exceeds the {max_change:.1f}% automatic limit")
    auto_approve = bool(settings.get("ebay_revision_auto_approve_enabled", False)) and guard_passed and not exceeds_auto_limit
    if not reasons:
        reasons.append(
            f"Projected profit ${projected_profit:.2f}; awaiting approval"
            if not auto_approve
            else f"Projected profit ${projected_profit:.2f}; approved by guarded automation"
        )
    return {
        "source_price": source_price,
        "source_shipping": source_shipping,
        "projected_profit": projected_profit,
        "minimum_profit": minimum_profit,
        "guard_passed": guard_passed,
        "guard_reason": "; ".join(reasons),
        "approval_required": not auto_approve,
        "approved_at": _now() if auto_approve else None,
        "status": EbayRevisionJobStatus.queued.value if auto_approve else EbayRevisionJobStatus.needs_review.value,
    }


def _apply_evidence(job: EbayRevisionJob, evidence: dict) -> None:
    for key, value in evidence.items():
        setattr(job, key, value)


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
            .where(EbayRevisionJob.status.in_(ACTIVE_STATUSES - {EbayRevisionJobStatus.running.value}))
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
            _apply_evidence(active_job, _revision_evidence(db, listing.product_id, target_price, listing.price))
            active_job.message = f"Target updated to ${target_price:.2f}; safety review reset."
            updated += 1
            continue
        evidence = _revision_evidence(db, listing.product_id, target_price, listing.price)
        db.add(
            EbayRevisionJob(
                product_id=listing.product_id,
                ebay_listing_id=listing.id,
                ebay_account_key=listing.account_id or "manual",
                old_price=listing.price,
                target_price=target_price,
                message=(
                    f"Proposed eBay price update from {_price(listing.price)} to ${target_price:.2f}. "
                    f"{evidence['guard_reason']}."
                ),
                **evidence,
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
    if read_pricing_settings(db).get("ebay_revision_execution_mode") != "browser_fallback":
        return None
    release_expired_ebay_revision_jobs(db)
    running = db.scalar(
        select(EbayRevisionJob)
        .where(
            EbayRevisionJob.status == EbayRevisionJobStatus.running.value,
            EbayRevisionJob.guard_passed.is_(True),
            EbayRevisionJob.approval_required.is_(False),
            EbayRevisionJob.approved_at.is_not(None),
        )
        .order_by(EbayRevisionJob.started_at.asc(), EbayRevisionJob.id.asc())
    )
    if running is not None:
        return running
    job = db.scalar(
        select(EbayRevisionJob)
        .where(
            EbayRevisionJob.status == EbayRevisionJobStatus.queued.value,
            EbayRevisionJob.guard_passed.is_(True),
            EbayRevisionJob.approval_required.is_(False),
            EbayRevisionJob.approved_at.is_not(None),
        )
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
    job.lease_expires_at = _now() + timedelta(minutes=REVISION_LEASE_MINUTES)
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
        if status == EbayRevisionJobStatus.queued.value and not job.guard_passed:
            raise ValueError(job.guard_reason or "Revision did not pass its safety guard")
        job.status = status
        if status in {
            EbayRevisionJobStatus.completed.value,
            EbayRevisionJobStatus.failed.value,
            EbayRevisionJobStatus.cancelled.value,
        }:
            job.completed_at = _now()
            job.lease_expires_at = None
        if status == EbayRevisionJobStatus.queued.value:
            job.started_at = None
            job.completed_at = None
            job.lease_expires_at = None
        if status == EbayRevisionJobStatus.completed.value:
            listing = db.get(EbayListing, job.ebay_listing_id)
            if listing is not None:
                listing.price = job.target_price
    if message is not None:
        job.message = message
    db.commit()
    db.refresh(job)
    return job


def approve_ebay_revision_job(db: Session, job: EbayRevisionJob) -> EbayRevisionJob:
    if not job.guard_passed:
        raise ValueError(job.guard_reason or "Revision did not pass its safety guard")
    if job.status not in {
        EbayRevisionJobStatus.needs_review.value,
        EbayRevisionJobStatus.paused.value,
        EbayRevisionJobStatus.failed.value,
    }:
        raise ValueError(f"Revision cannot be approved from {job.status}")
    job.approved_at = _now()
    job.approval_required = False
    job.status = EbayRevisionJobStatus.queued.value
    job.started_at = None
    job.completed_at = None
    job.lease_expires_at = None
    job.message = f"Approved eBay price update from {_price(job.old_price)} to ${job.target_price:.2f}."
    db.commit()
    db.refresh(job)
    return job


def release_expired_ebay_revision_jobs(db: Session, now: datetime | None = None) -> int:
    checked_at = now or _now()
    expired = list(
        db.scalars(
            select(EbayRevisionJob).where(
                EbayRevisionJob.status == EbayRevisionJobStatus.running.value,
                EbayRevisionJob.lease_expires_at.is_not(None),
                EbayRevisionJob.lease_expires_at < checked_at,
            )
        ).all()
    )
    for job in expired:
        job.lease_expires_at = None
        if job.attempts >= MAX_REVISION_ATTEMPTS:
            job.status = EbayRevisionJobStatus.failed.value
            job.completed_at = checked_at
            job.message = f"Revision timed out after {job.attempts} attempts; manual attention required."
        else:
            job.status = EbayRevisionJobStatus.queued.value
            job.started_at = None
            job.message = "Revision lease expired; returned to the Windows queue."
    if expired:
        db.commit()
    return len(expired)


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
        "source_price": job.source_price,
        "source_shipping": job.source_shipping,
        "projected_profit": job.projected_profit,
        "minimum_profit": job.minimum_profit,
        "guard_passed": job.guard_passed,
        "guard_reason": job.guard_reason,
        "approval_required": job.approval_required,
        "approved_at": job.approved_at,
        "lease_expires_at": job.lease_expires_at,
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
        "autozs_autosubmit": "1",
    }
    return f"https://www.ebay.com/sl/list?{urlencode(params)}"


def _now() -> datetime:
    return datetime.utcnow()


def _price(value: float | None) -> str:
    return "the unknown stored price" if value is None else f"${value:.2f}"

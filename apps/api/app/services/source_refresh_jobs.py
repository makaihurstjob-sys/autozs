from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.domain import AutomationRun, EbayListing, Product, ProductStatus, SourceRefreshJob, SourceRefreshJobStatus
from app.services.ebay_revisions import enqueue_ebay_price_revisions
from app.services.importer import recalculate_all_draft_prices
from app.services.settings import read_pricing_settings


LEASE_MINUTES = 10
AUTO_REFRESH_LISTING_STATUSES = {"scheduled", "listed", "live", "active"}


def _runner_url(job: SourceRefreshJob, source_url: str) -> str:
    separator = "&" if "?" in source_url else "?"
    return (
        f"{source_url}{separator}ea_auto_import=1"
        f"&autozs_refresh_job={job.id}&autozs_refresh_batch={job.batch_key}"
    )


def serialize_source_refresh_job(db: Session, job: SourceRefreshJob) -> dict:
    product = db.scalar(
        select(Product).options(selectinload(Product.supplier_products)).where(Product.id == job.product_id)
    )
    supplier = product.supplier_products[0] if product and product.supplier_products else None
    source_url = supplier.source_url if supplier else ""
    return {
        "id": job.id,
        "batch_key": job.batch_key,
        "product_id": job.product_id,
        "sku": product.sku if product else f"product-{job.product_id}",
        "title": product.title if product else "Missing product",
        "source_url": source_url,
        "runner_url": _runner_url(job, source_url) if source_url else "",
        "status": job.status,
        "attempts": job.attempts,
        "baseline_price": job.baseline_price,
        "captured_price": job.captured_price,
        "price_changed": job.price_changed,
        "revision_queued": job.revision_queued,
        "message": job.message,
        "scheduled_for": job.scheduled_for,
        "lease_expires_at": job.lease_expires_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def create_source_refresh_batch(
    db: Session,
    *,
    limit: int = 5,
    interval_hours: float = 6.0,
    force: bool = False,
    product_ids: set[int] | None = None,
) -> tuple[str, int, list[SourceRefreshJob]]:
    now = datetime.utcnow()
    release_expired_source_refresh_jobs(db, now=now)
    cutoff = now - timedelta(hours=interval_hours)
    query = (
        select(Product)
        .options(selectinload(Product.supplier_products))
        .where(Product.status != ProductStatus.deleted.value)
        .order_by(Product.created_at.asc(), Product.id.asc())
    )
    if product_ids is not None:
        if not product_ids:
            return f"refresh-{now:%Y%m%d%H%M%S}-{uuid4().hex[:6]}", 0, []
        query = query.where(Product.id.in_(product_ids))
    products = db.scalars(query).all()
    due: list[tuple[Product, object]] = []
    for product in products:
        supplier = product.supplier_products[0] if product.supplier_products else None
        if supplier is None or not supplier.source_url:
            continue
        if force or supplier.updated_at <= cutoff or supplier.last_price is None:
            due.append((product, supplier))
    due.sort(key=lambda item: (item[1].updated_at, item[0].id))

    batch_key = f"refresh-{now:%Y%m%d%H%M%S}-{uuid4().hex[:6]}"
    jobs: list[SourceRefreshJob] = []
    for product, supplier in due[:limit]:
        active = db.scalar(
            select(SourceRefreshJob).where(
                SourceRefreshJob.product_id == product.id,
                SourceRefreshJob.status.in_((SourceRefreshJobStatus.queued.value, SourceRefreshJobStatus.running.value)),
            )
        )
        if active is not None:
            continue
        job = SourceRefreshJob(
            batch_key=batch_key,
            product_id=product.id,
            status=SourceRefreshJobStatus.queued.value,
            scheduled_for=now,
            baseline_price=supplier.last_price,
            message="Waiting for browser capture",
        )
        db.add(job)
        jobs.append(job)
    db.commit()
    for job in jobs:
        db.refresh(job)
    return batch_key, len(due), jobs


def create_automatic_source_refresh_batch(db: Session) -> tuple[str | None, int, list[SourceRefreshJob], str]:
    settings = read_pricing_settings(db)
    if not bool(settings.get("source_refresh_auto_enabled", True)):
        message = "Automatic source refresh is disabled."
        return None, 0, [], message
    interval_hours = float(settings.get("source_refresh_interval_hours", 6) or 6)
    limit = max(1, min(150, int(float(settings.get("source_refresh_auto_batch_size", 5) or 5))))
    eligible_product_ids = set(
        db.scalars(
            select(EbayListing.product_id).where(EbayListing.status.in_(AUTO_REFRESH_LISTING_STATUSES))
        ).all()
    )
    if not eligible_product_ids:
        return None, 0, [], "No scheduled or live listings are eligible for automatic source refresh."
    batch_key, due_available, jobs = create_source_refresh_batch(
        db,
        limit=limit,
        interval_hours=interval_hours,
        force=False,
        product_ids=eligible_product_ids,
    )
    if jobs:
        message = (
            f"Queued {len(jobs)} supplier price refresh job(s) for Windows Chrome "
            f"({due_available} due; {interval_hours:g}-hour interval)."
        )
        db.add(AutomationRun(task_name="source_refresh_scheduler", status="completed", message=message))
        db.commit()
        for job in jobs:
            db.refresh(job)
        return batch_key, due_available, jobs, message
    message = f"No scheduled or live supplier prices are due inside the {interval_hours:g}-hour window."
    return batch_key, due_available, jobs, message


def release_expired_source_refresh_jobs(db: Session, now: datetime | None = None) -> int:
    checked_at = now or datetime.utcnow()
    expired = db.scalars(
        select(SourceRefreshJob).where(
            SourceRefreshJob.status == SourceRefreshJobStatus.running.value,
            SourceRefreshJob.lease_expires_at < checked_at,
        )
    ).all()
    for job in expired:
        job.status = SourceRefreshJobStatus.queued.value
        job.lease_expires_at = None
        job.message = "Lease expired; returned to queue"
    if expired:
        db.commit()
    return len(expired)


def claim_next_source_refresh_job_any_batch(db: Session) -> SourceRefreshJob | None:
    release_expired_source_refresh_jobs(db)
    queued = db.scalar(
        select(SourceRefreshJob)
        .where(
            SourceRefreshJob.status == SourceRefreshJobStatus.queued.value,
            SourceRefreshJob.scheduled_for <= datetime.utcnow(),
        )
        .order_by(SourceRefreshJob.created_at.asc(), SourceRefreshJob.id.asc())
    )
    if queued is None:
        return None
    return claim_next_source_refresh_job(db, queued.batch_key)


def source_refresh_has_running_job(db: Session) -> bool:
    release_expired_source_refresh_jobs(db)
    return (
        db.scalar(
            select(SourceRefreshJob.id)
            .where(SourceRefreshJob.status == SourceRefreshJobStatus.running.value)
            .order_by(SourceRefreshJob.started_at.asc(), SourceRefreshJob.id.asc())
        )
        is not None
    )


def claim_next_source_refresh_job(db: Session, batch_key: str) -> SourceRefreshJob | None:
    now = datetime.utcnow()
    release_expired_source_refresh_jobs(db, now=now)

    job = db.scalar(
        select(SourceRefreshJob)
        .where(
            SourceRefreshJob.batch_key == batch_key,
            SourceRefreshJob.status == SourceRefreshJobStatus.queued.value,
            SourceRefreshJob.scheduled_for <= now,
        )
        .order_by(SourceRefreshJob.id.asc())
    )
    if job is None:
        db.commit()
        return None
    job.status = SourceRefreshJobStatus.running.value
    job.started_at = job.started_at or now
    job.lease_expires_at = now + timedelta(minutes=LEASE_MINUTES)
    job.attempts += 1
    job.message = "Browser capture in progress"
    db.commit()
    db.refresh(job)
    return job


def complete_source_refresh_job(db: Session, job_id: int, product_id: int) -> SourceRefreshJob | None:
    job = db.get(SourceRefreshJob, job_id)
    if job is None or job.product_id != product_id:
        return None
    product = db.scalar(
        select(Product).options(selectinload(Product.supplier_products)).where(Product.id == product_id)
    )
    supplier = product.supplier_products[0] if product and product.supplier_products else None
    captured = supplier.last_price if supplier else None
    job.captured_price = captured
    job.price_changed = captured is not None and job.baseline_price is not None and abs(captured - job.baseline_price) >= 0.01
    job.status = SourceRefreshJobStatus.completed.value
    job.completed_at = datetime.utcnow()
    job.lease_expires_at = None
    job.message = "Price changed" if job.price_changed else "Price confirmed"
    db.commit()
    if job.price_changed:
        recalculate_all_draft_prices(db, product_ids=[product_id])
        queued, updated = enqueue_ebay_price_revisions(db, product_ids=[product_id])
        job.revision_queued = bool(queued or updated)
        job.message = f"Price changed; {queued + updated} eBay revision job(s) queued"
        db.commit()
    db.refresh(job)
    return job


def fail_source_refresh_job(db: Session, job_id: int, message: str) -> SourceRefreshJob | None:
    job = db.get(SourceRefreshJob, job_id)
    if job is None:
        return None
    job.status = SourceRefreshJobStatus.failed.value
    job.completed_at = datetime.utcnow()
    job.lease_expires_at = None
    job.message = message[:1000]
    db.commit()
    db.refresh(job)
    return job


def list_source_refresh_jobs(db: Session, batch_key: str | None = None, limit: int = 100) -> list[SourceRefreshJob]:
    statement = select(SourceRefreshJob).order_by(SourceRefreshJob.created_at.desc(), SourceRefreshJob.id.desc()).limit(limit)
    if batch_key:
        statement = statement.where(SourceRefreshJob.batch_key == batch_key)
    return list(db.scalars(statement).all())

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.domain import (
    EbayRevisionBatch,
    EbayRevisionBatchStatus,
    EbayRevisionJob,
    EbayRevisionJobStatus,
    ListingJob,
    ListingJobStatus,
    OperationalAlert,
    OperationalAlertSeverity,
    OperationalAlertStatus,
    Product,
    SourceRefreshJob,
    SourceRefreshJobStatus,
    SupplierProduct,
)
from app.services.workers import list_workers


ACTIVE_STATUSES = {OperationalAlertStatus.open.value, OperationalAlertStatus.acknowledged.value}
VISIBLE_STATUSES = ACTIVE_STATUSES | {OperationalAlertStatus.dismissed.value}
STALE_JOB_AFTER = timedelta(minutes=45)
STALE_BATCH_AFTER = timedelta(minutes=45)


def refresh_operational_alerts(db: Session, now: datetime | None = None) -> list[OperationalAlert]:
    checked_at = now or datetime.utcnow()
    specs = _build_alert_specs(db, checked_at)
    active_keys = {spec["key"] for spec in specs}
    existing = {
        alert.key: alert
        for alert in db.scalars(select(OperationalAlert).where(OperationalAlert.key.in_(active_keys))).all()
    } if active_keys else {}

    for spec in specs:
        alert = existing.get(spec["key"])
        if alert is None:
            alert = OperationalAlert(
                key=spec["key"],
                first_seen_at=checked_at,
                status=OperationalAlertStatus.open.value,
            )
            db.add(alert)
        elif alert.status == OperationalAlertStatus.resolved.value:
            alert.status = OperationalAlertStatus.open.value
            alert.resolved_at = None
            alert.dismissed_at = None
        _apply_alert_spec(alert, spec, checked_at)

    stale_query = select(OperationalAlert).where(OperationalAlert.status.in_(ACTIVE_STATUSES))
    if active_keys:
        stale_query = stale_query.where(~OperationalAlert.key.in_(active_keys))
    stale_alerts = db.scalars(stale_query).all()
    for alert in stale_alerts:
        alert.status = OperationalAlertStatus.resolved.value
        alert.resolved_at = checked_at
        alert.last_seen_at = checked_at

    db.commit()
    return list_operational_alerts(db, status="active", limit=100, refresh=False)


def list_operational_alerts(
    db: Session,
    status: str = "active",
    limit: int = 100,
    refresh: bool = True,
) -> list[OperationalAlert]:
    if refresh:
        refresh_operational_alerts(db)
    query = select(OperationalAlert)
    if status == "active":
        query = query.where(OperationalAlert.status.in_(ACTIVE_STATUSES))
    elif status != "all":
        query = query.where(OperationalAlert.status == status)
    return list(
        db.scalars(
            query.order_by(
                OperationalAlert.severity.desc(),
                OperationalAlert.last_seen_at.desc(),
                OperationalAlert.id.desc(),
            ).limit(limit)
        ).all()
    )


def summarize_operational_alerts(db: Session) -> dict[str, int]:
    refresh_operational_alerts(db)
    rows = db.execute(
        select(OperationalAlert.status, OperationalAlert.severity, func.count(OperationalAlert.id))
        .group_by(OperationalAlert.status, OperationalAlert.severity)
    ).all()
    summary = {
        "open": 0,
        "acknowledged": 0,
        "resolved": 0,
        "dismissed": 0,
        "critical": 0,
        "warning": 0,
        "info": 0,
        "active": 0,
    }
    for status, severity, count in rows:
        count = int(count or 0)
        if status in summary:
            summary[status] += count
        if severity in summary and status in ACTIVE_STATUSES:
            summary[severity] += count
        if status in ACTIVE_STATUSES:
            summary["active"] += count
    return summary


def update_operational_alert_status(db: Session, alert_id: int, status: str) -> OperationalAlert | None:
    alert = db.get(OperationalAlert, alert_id)
    if alert is None:
        return None
    now = datetime.utcnow()
    alert.status = status
    if status == OperationalAlertStatus.dismissed.value:
        alert.dismissed_at = now
    elif status == OperationalAlertStatus.resolved.value:
        alert.resolved_at = now
    elif status == OperationalAlertStatus.open.value:
        alert.dismissed_at = None
        alert.resolved_at = None
    db.commit()
    db.refresh(alert)
    return alert


def _build_alert_specs(db: Session, now: datetime) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    specs.extend(_worker_alert_specs(db))
    specs.extend(_source_refresh_alert_specs(db, now))
    specs.extend(_ebay_revision_alert_specs(db, now))
    specs.extend(_listing_job_alert_specs(db, now))
    specs.extend(_supplier_alert_specs(db))
    return specs


def _worker_alert_specs(db: Session) -> list[dict[str, Any]]:
    workers = list_workers(db)
    if not workers:
        return [
            _spec(
                key="worker:none",
                severity=OperationalAlertSeverity.critical.value,
                source="worker",
                title="No AutoZS worker heartbeats",
                message="No Windows or local worker has checked in yet.",
            )
        ]
    specs: list[dict[str, Any]] = []
    for worker in workers:
        status = str(worker.get("status") or "")
        if status == "online":
            continue
        label = str(worker.get("label") or worker.get("worker_id") or "AutoZS worker")
        specs.append(
            _spec(
                key=f"worker:{worker.get('worker_id')}:{status}",
                severity=OperationalAlertSeverity.critical.value if status == "offline" else OperationalAlertSeverity.warning.value,
                source="worker",
                title=f"{label} is {status}",
                message=f"Last heartbeat was {worker.get('seconds_since_seen') or 'unknown'} seconds ago.",
            )
        )
    return specs


def _source_refresh_alert_specs(db: Session, now: datetime) -> list[dict[str, Any]]:
    failed = db.scalars(
        select(SourceRefreshJob)
        .where(SourceRefreshJob.status == SourceRefreshJobStatus.failed.value)
        .order_by(SourceRefreshJob.updated_at.desc())
        .limit(50)
    ).all()
    failed = [
        job
        for job in failed
        if db.scalar(
            select(SourceRefreshJob.id)
            .where(
                SourceRefreshJob.product_id == job.product_id,
                SourceRefreshJob.id > job.id,
                SourceRefreshJob.status == SourceRefreshJobStatus.completed.value,
            )
            .limit(1)
        )
        is None
    ]
    stale = db.scalars(
        select(SourceRefreshJob).where(
            SourceRefreshJob.status == SourceRefreshJobStatus.running.value,
            SourceRefreshJob.updated_at < now - STALE_JOB_AFTER,
        )
    ).all()
    specs: list[dict[str, Any]] = []
    for job in failed:
        product = db.get(Product, job.product_id)
        specs.append(
            _spec(
                key=f"source-refresh:{job.id}:failed",
                severity=OperationalAlertSeverity.warning.value,
                source="source-refresh",
                title=f"Source refresh failed for {_title(product, job.product_id)}",
                message=job.message or "Supplier price capture failed.",
                product_id=job.product_id,
                job_type="source-refresh",
                job_id=job.id,
            )
        )
    for job in stale:
        product = db.get(Product, job.product_id)
        specs.append(
            _spec(
                key=f"source-refresh:{job.id}:stuck",
                severity=OperationalAlertSeverity.warning.value,
                source="source-refresh",
                title=f"Source refresh looks stuck for {_title(product, job.product_id)}",
                message="The supplier capture job has been running longer than expected.",
                product_id=job.product_id,
                job_type="source-refresh",
                job_id=job.id,
            )
        )
    return specs


def _ebay_revision_alert_specs(db: Session, now: datetime) -> list[dict[str, Any]]:
    job_statuses = [
        EbayRevisionJobStatus.failed.value,
        EbayRevisionJobStatus.needs_review.value,
        EbayRevisionJobStatus.paused.value,
    ]
    jobs = db.scalars(
        select(EbayRevisionJob)
        .where(EbayRevisionJob.status.in_(job_statuses))
        .order_by(EbayRevisionJob.updated_at.desc())
        .limit(50)
    ).all()
    batches = db.scalars(
        select(EbayRevisionBatch).where(
            or_(
                EbayRevisionBatch.status.in_([EbayRevisionBatchStatus.failed.value, EbayRevisionBatchStatus.needs_review.value]),
                and_(
                    EbayRevisionBatch.status == EbayRevisionBatchStatus.waiting_results.value,
                    EbayRevisionBatch.updated_at < now - STALE_BATCH_AFTER,
                ),
            )
        )
    ).all()
    specs: list[dict[str, Any]] = []
    for job in jobs:
        product = db.get(Product, job.product_id)
        specs.append(
            _spec(
                key=f"ebay-revision-job:{job.id}:{job.status}",
                severity=OperationalAlertSeverity.warning.value,
                source="ebay-revision",
                title=f"eBay price revision needs attention for {_title(product, job.product_id)}",
                message=job.message or job.guard_reason or "A price revision needs review.",
                product_id=job.product_id,
                listing_id=job.ebay_listing_id,
                job_type="ebay-revision-job",
                job_id=job.id,
            )
        )
    for batch in batches:
        specs.append(
            _spec(
                key=f"ebay-revision-batch:{batch.id}:{batch.status}",
                severity=OperationalAlertSeverity.warning.value,
                source="ebay-revision",
                title=f"eBay revision batch needs attention: {batch.filename}",
                message=batch.message or "The eBay revision upload/result flow did not complete.",
                job_type="ebay-revision-batch",
                job_id=batch.id,
            )
        )
    return specs


def _listing_job_alert_specs(db: Session, now: datetime) -> list[dict[str, Any]]:
    statuses = [ListingJobStatus.failed.value, ListingJobStatus.needs_review.value, ListingJobStatus.paused.value]
    jobs = db.scalars(
        select(ListingJob)
        .where(
            or_(
                ListingJob.status.in_(statuses),
                and_(ListingJob.status == ListingJobStatus.running.value, ListingJob.updated_at < now - STALE_JOB_AFTER),
            )
        )
        .order_by(ListingJob.updated_at.desc())
        .limit(50)
    ).all()
    specs: list[dict[str, Any]] = []
    for job in jobs:
        product = db.get(Product, job.product_id)
        stuck = job.status == ListingJobStatus.running.value
        specs.append(
            _spec(
                key=f"listing-job:{job.id}:{'stuck' if stuck else job.status}",
                severity=OperationalAlertSeverity.warning.value,
                source="listing-job",
                title=f"Listing job {'looks stuck' if stuck else 'needs attention'} for {_title(product, job.product_id)}",
                message=job.message or "The eBay listing workflow needs review.",
                product_id=job.product_id,
                job_type="listing-job",
                job_id=job.id,
            )
        )
    return specs


def _supplier_alert_specs(db: Session) -> list[dict[str, Any]]:
    products = db.scalars(
        select(SupplierProduct)
        .where(SupplierProduct.in_stock == False)  # noqa: E712
        .order_by(SupplierProduct.updated_at.desc())
        .limit(50)
    ).all()
    specs: list[dict[str, Any]] = []
    for supplier in products:
        product = db.get(Product, supplier.product_id)
        specs.append(
            _spec(
                key=f"supplier-product:{supplier.id}:out-of-stock",
                severity=OperationalAlertSeverity.critical.value,
                source="supplier",
                title=f"Supplier product may be out of stock: {_title(product, supplier.product_id)}",
                message=f"{supplier.supplier} source is marked out of stock.",
                product_id=supplier.product_id,
            )
        )
    return specs


def _apply_alert_spec(alert: OperationalAlert, spec: dict[str, Any], now: datetime) -> None:
    if alert.status not in VISIBLE_STATUSES:
        alert.status = OperationalAlertStatus.open.value
    alert.severity = spec["severity"]
    alert.source = spec["source"]
    alert.title = spec["title"]
    alert.message = spec.get("message") or ""
    alert.product_id = spec.get("product_id")
    alert.listing_id = spec.get("listing_id")
    alert.job_type = spec.get("job_type")
    alert.job_id = spec.get("job_id")
    alert.action_url = spec.get("action_url")
    alert.last_seen_at = now


def _spec(**values: Any) -> dict[str, Any]:
    return values


def _title(product: Product | None, fallback_id: int | None) -> str:
    if product is None:
        return f"product {fallback_id or 'unknown'}"
    return product.title or product.sku or f"product {product.id}"

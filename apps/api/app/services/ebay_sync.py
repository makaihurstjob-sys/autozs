from datetime import datetime
import re
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import (
    EbayListing,
    EbaySyncRun,
    EbaySyncRunStatus,
    ListingDraft,
    ListingJob,
    ListingJobStatus,
    Product,
    ProductStatus,
)
from app.services.ebay_browser_account import assert_ebay_browser_account_can_list
from app.services.ebay_revisions import cancel_revision_jobs_for_ebay_listing, enqueue_ebay_price_revisions


ACTIVE_REPORT_STATUSES = {"active", "live", "listed"}
ACTIVE_REPORT_RECONCILE_STATUSES = {*ACTIVE_REPORT_STATUSES, "scheduled"}


def start_ebay_sync_run(db: Session, account_key: str = "manual", source: str = "seller_hub_report") -> EbaySyncRun:
    run = EbaySyncRun(
        account_key=_clean_account_key(account_key),
        source=source[:64],
        report_type="active_listings",
        status=EbaySyncRunStatus.running.value,
        phase="account_check",
        started_at=_now(),
        message="Checking the visible Chrome eBay account before syncing.",
    )
    db.add(run)
    db.flush()
    try:
        assert_ebay_browser_account_can_list(db, run.account_key)
    except ValueError as exc:
        run.status = EbaySyncRunStatus.needs_review.value
        run.phase = "account_check"
        run.completed_at = _now()
        run.message = str(exc)
    else:
        run.phase = "opening_reports"
        run.message = "Account matched. Opening Seller Hub Reports for automatic Active Listings sync."
    db.commit()
    db.refresh(run)
    return run


def list_ebay_sync_runs(db: Session, account_key: str | None = None, limit: int = 25) -> list[EbaySyncRun]:
    stmt = select(EbaySyncRun).order_by(EbaySyncRun.created_at.desc(), EbaySyncRun.id.desc()).limit(limit)
    if account_key:
        stmt = stmt.where(EbaySyncRun.account_key == _clean_account_key(account_key))
    return list(db.scalars(stmt).all())


def import_listing_report_rows(
    db: Session,
    rows: list[dict[str, Any]],
    account_key: str = "manual",
    run_id: int | None = None,
    source: str = "manual_report",
    tombstone_missing: bool = True,
) -> EbaySyncRun:
    account_key = _clean_account_key(account_key)
    run = db.get(EbaySyncRun, run_id) if run_id is not None else None
    if run is None:
        run = EbaySyncRun(
            account_key=account_key,
            source=source[:64],
            status=EbaySyncRunStatus.running.value,
            phase="listing_report",
            started_at=_now(),
        )
        db.add(run)
        db.flush()
    else:
        run.account_key = account_key or run.account_key
        run.source = source[:64]
        run.status = EbaySyncRunStatus.running.value
        run.phase = "listing_report"
        run.started_at = run.started_at or _now()
        run.completed_at = None

    normalized_rows = [_normalize_listing_row(row) for row in rows]
    normalized_rows = [row for row in normalized_rows if row["listing_id"]]
    seen_listing_ids: set[str] = set()
    upserted = 0
    imported = 0
    touched_product_ids: set[int] = set()

    for row in normalized_rows:
        listing_id = row["listing_id"]
        seen_listing_ids.add(listing_id)
        listing = db.scalar(
            select(EbayListing).where(EbayListing.account_id == account_key, EbayListing.listing_id == listing_id)
        )
        product = _find_product_for_report_row(db, row, listing)
        if product is None:
            product = _create_placeholder_product(db, row)
            imported += 1
        if listing is None:
            listing = EbayListing(product_id=product.id, listing_id=listing_id, account_id=account_key)
            db.add(listing)
        listing.product_id = product.id
        listing.environment = row["environment"]
        listing.price = row["price"]
        listing.quantity = row["quantity"]
        listing.status = row["status"]
        if row["started_at"] is not None:
            listing.started_at = row["started_at"]
        if row["renews_at"] is not None:
            listing.renews_at = row["renews_at"]
        if row["views"] is not None:
            listing.views = row["views"]
        _sync_local_draft_status(db, product.id, row)
        touched_product_ids.add(product.id)
        upserted += 1

    tombstoned = _tombstone_missing_listings(db, account_key, seen_listing_ids) if tombstone_missing else 0
    if touched_product_ids:
        revision_queued, _revision_updated = enqueue_ebay_price_revisions(db, product_ids=sorted(touched_product_ids))
    else:
        revision_queued = 0

    run.listings_seen = len(normalized_rows)
    run.listings_upserted = upserted
    run.listings_imported = imported
    run.listings_tombstoned = tombstoned
    run.revision_jobs_queued = revision_queued
    run.status = EbaySyncRunStatus.completed.value
    run.phase = "completed"
    run.completed_at = _now()
    run.message = (
        f"Synced {len(normalized_rows)} listing rows for {account_key}. "
        f"Upserted {upserted}, imported {imported}, tombstoned {tombstoned}."
    )
    db.commit()
    db.refresh(run)
    return run


def serialize_ebay_sync_run(run: EbaySyncRun) -> dict:
    runner_url = "https://www.ebay.com/sh/reports/downloads#" + urlencode(
        {
            "autozs_sync_run": run.id,
            "autozs_account_key": run.account_key,
            "autozs_report_type": run.report_type,
        }
    )
    return {
        "id": run.id,
        "account_key": run.account_key,
        "status": run.status,
        "phase": run.phase,
        "source": run.source,
        "report_type": run.report_type,
        "report_reference": run.report_reference,
        "report_filename": run.report_filename,
        "attempts": run.attempts,
        "runner_url": runner_url,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "listings_seen": run.listings_seen,
        "listings_upserted": run.listings_upserted,
        "listings_imported": run.listings_imported,
        "listings_tombstoned": run.listings_tombstoned,
        "orders_seen": run.orders_seen,
        "orders_upserted": run.orders_upserted,
        "revision_jobs_queued": run.revision_jobs_queued,
        "message": run.message,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def update_ebay_sync_run_progress(db: Session, run_id: int, values: dict[str, Any]) -> EbaySyncRun | None:
    run = db.get(EbaySyncRun, run_id)
    if run is None:
        return None
    allowed_phases = {
        "opening_reports",
        "report_page_ready",
        "requesting_report",
        "waiting_for_report",
        "downloading_report",
        "report_downloaded",
        "importing_report",
    }
    phase = str(values.get("phase") or "").strip()
    if phase and phase not in allowed_phases:
        raise ValueError(f"Unsupported eBay sync phase: {phase}")
    status = str(values.get("status") or "").strip()
    if status and status not in {
        EbaySyncRunStatus.running.value,
        EbaySyncRunStatus.needs_review.value,
        EbaySyncRunStatus.failed.value,
    }:
        raise ValueError(f"Unsupported eBay sync status: {status}")
    if phase:
        run.phase = phase
    if status:
        run.status = status
    if values.get("message") is not None:
        run.message = str(values["message"])[:2000]
    if values.get("report_reference") is not None:
        run.report_reference = str(values["report_reference"])[:128] or None
    if values.get("report_filename") is not None:
        run.report_filename = str(values["report_filename"])[:1000] or None
    if values.get("increment_attempts"):
        run.attempts += 1
    if run.status in {EbaySyncRunStatus.needs_review.value, EbaySyncRunStatus.failed.value}:
        run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run


def _find_product_for_report_row(db: Session, row: dict[str, Any], listing: EbayListing | None) -> Product | None:
    if listing is not None:
        product = db.get(Product, listing.product_id)
        if product is not None:
            return product
    if row["sku"]:
        product = db.scalar(select(Product).where(Product.sku == row["sku"]))
        if product is not None:
            return product
    return None


def _create_placeholder_product(db: Session, row: dict[str, Any]) -> Product:
    sku = _unique_placeholder_sku(db, row["sku"] or f"EBAY-{row['listing_id']}")
    product = Product(
        sku=sku,
        title=row["title"] or f"Imported eBay listing {row['listing_id']}",
        status=ProductStatus.monitoring.value,
        competitor_price=row["price"],
    )
    db.add(product)
    db.flush()
    db.add(
        ListingDraft(
            product_id=product.id,
            marketplace="ebay",
            title=product.title,
            description="Imported from an eBay Seller Hub sync report. Add supplier details before repricing.",
            source_price=None,
            calculated_price=row["price"],
            status=row["status"],
        )
    )
    db.flush()
    return product


def _sync_local_draft_status(db: Session, product_id: int, row: dict[str, Any]) -> None:
    draft = db.scalar(select(ListingDraft).where(ListingDraft.product_id == product_id, ListingDraft.marketplace == "ebay"))
    if draft is not None:
        draft.status = row["status"]
        if row["price"] is not None:
            draft.calculated_price = row["price"]
    draft_id = row["draft_id"]
    if draft_id:
        job = db.scalar(
            select(ListingJob)
            .where(ListingJob.product_id == product_id)
            .where(ListingJob.ebay_draft_id == draft_id)
            .order_by(ListingJob.created_at.desc(), ListingJob.id.desc())
        )
        if job is not None:
            is_live = row["status"] in {"active", "live", "listed"}
            job.status = ListingJobStatus.completed.value if is_live else ListingJobStatus.saved_draft.value
            job.completed_at = _now()
            label = "live listing" if is_live else "draft"
            job.message = f"Verified {label} by eBay sync report row {row['listing_id']}."


def _tombstone_missing_listings(db: Session, account_key: str, seen_listing_ids: set[str]) -> int:
    if not seen_listing_ids:
        return 0
    tombstoned = 0
    now = _now()
    listings = db.scalars(
        select(EbayListing)
        .where(EbayListing.account_id == account_key)
        .where(EbayListing.status.in_(ACTIVE_REPORT_RECONCILE_STATUSES))
    ).all()
    for listing in listings:
        if listing.listing_id in seen_listing_ids:
            continue
        if not _missing_active_report_row_should_tombstone(db, listing, now):
            continue
        listing.status = "tombstoned"
        draft = db.scalar(select(ListingDraft).where(ListingDraft.product_id == listing.product_id, ListingDraft.marketplace == "ebay"))
        if draft is not None:
            draft.status = "tombstoned"
        cancel_revision_jobs_for_ebay_listing(
            db,
            listing,
            reason="Cancelled because Seller Hub no longer reports this listing as active.",
            commit=False,
        )
        _tombstone_stale_scheduled_jobs(db, listing)
        tombstoned += 1
    return tombstoned


def _missing_active_report_row_should_tombstone(db: Session, listing: EbayListing, now: datetime) -> bool:
    status = str(listing.status or "").lower()
    if status in ACTIVE_REPORT_STATUSES:
        return True
    if status != "scheduled":
        return False
    job = db.scalar(
        select(ListingJob)
        .where(ListingJob.product_id == listing.product_id)
        .where(ListingJob.ebay_account_key == listing.account_id)
        .where(ListingJob.listing_schedule_at.is_not(None))
        .order_by(ListingJob.listing_schedule_at.desc(), ListingJob.created_at.desc(), ListingJob.id.desc())
    )
    if job is None or job.listing_schedule_at is None:
        return False
    return job.listing_schedule_at <= now


def _tombstone_stale_scheduled_jobs(db: Session, listing: EbayListing) -> None:
    jobs = db.scalars(
        select(ListingJob)
        .where(ListingJob.product_id == listing.product_id)
        .where(ListingJob.ebay_account_key == listing.account_id)
        .where(ListingJob.listing_schedule_at.is_not(None))
        .where(ListingJob.status.not_in((ListingJobStatus.tombstoned.value, ListingJobStatus.cancelled.value)))
    ).all()
    for job in jobs:
        job.status = ListingJobStatus.tombstoned.value
        job.completed_at = _now()
        job.message = "Scheduled listing was missing from the active Seller Hub report after its start time, so AutoZS tombstoned it."


def _normalize_listing_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {_normalize_key(key): value for key, value in dict(row).items()}
    listing_id = _first_text(normalized, "listing_id", "item_id", "item_number", "ebay_item_id")
    views = _first_text(normalized, "views", "view_count", "page_views", "listing_views")
    return {
        "listing_id": listing_id[:128],
        "draft_id": _first_text(normalized, "draft_id", "ebay_draft_id")[:128],
        "sku": _first_text(normalized, "sku", "custom_label", "custom_label_sku", "seller_sku")[:64],
        "title": _first_text(normalized, "title", "item_title", "listing_title")[:512],
        "status": _normalize_status(_first_text(normalized, "status", "listing_status", "state")),
        "price": _parse_money(_first_text(normalized, "price", "current_price", "start_price", "buy_it_now_price")),
        "quantity": _parse_int(_first_text(normalized, "quantity", "available_quantity", "qty"), default=1),
        "views": _parse_int(views, default=0) if views else None,
        "started_at": _parse_datetime(_first_text(normalized, "live_on", "started_at", "start_date", "listing_start_date")),
        "renews_at": _parse_datetime(_first_text(normalized, "renews_on", "renews_at", "renewal_date", "relist_date", "end_date", "ends_on")),
        "environment": _first_text(normalized, "environment")[:32] or "manual",
    }


def _normalize_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _normalize_status(value: str) -> str:
    status = _normalize_key(value).replace("_", " ")
    if "schedule" in status:
        return "scheduled"
    if "draft" in status:
        return "draft"
    if "active" in status or "live" in status or "listed" in status:
        return "active"
    if "sold" in status or "ended" in status:
        return "ended"
    return _normalize_key(value)[:32] or "active"


def _parse_money(value: str) -> float | None:
    cleaned = re.sub(r"[^0-9.\-]+", "", value or "")
    if not cleaned:
        return None
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def _parse_int(value: str, default: int = 0) -> int:
    cleaned = re.sub(r"[^0-9\-]+", "", value or "")
    if not cleaned:
        return default
    try:
        return int(cleaned)
    except ValueError:
        return default


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = re.sub(r"\s+", " ", text)
    normalized = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+(PDT|PST|MDT|MST|CDT|CST|EDT|EST)$", "", normalized, flags=re.IGNORECASE)
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed
    except ValueError:
        pass
    for pattern in (
        "%a, %b %d, %Y",
        "%b %d, %Y",
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%a, %b %d, %Y, %I:%M %p",
        "%b %d, %Y, %I:%M %p",
        "%m/%d/%Y %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%b-%d-%y %H:%M:%S",
    ):
        try:
            return datetime.strptime(normalized, pattern)
        except ValueError:
            continue
    return None


def _unique_placeholder_sku(db: Session, requested: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", requested.strip()).strip("-")[:58] or "EBAY-LISTING"
    sku = base
    index = 2
    while db.scalar(select(Product.id).where(Product.sku == sku)) is not None:
        suffix = f"-{index}"
        sku = f"{base[:64 - len(suffix)]}{suffix}"
        index += 1
    return sku


def _clean_account_key(value: str | None) -> str:
    return str(value or "manual").strip()[:128] or "manual"


def _now() -> datetime:
    return datetime.utcnow()

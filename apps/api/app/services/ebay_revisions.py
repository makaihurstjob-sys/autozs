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
    SourceRefreshJob,
    SourceRefreshJobStatus,
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
TERMINAL_REVISION_LISTING_STATUSES = {"tombstoned", "deleted", "ended", "cancelled", "inactive"}
REVISION_LEASE_MINUTES = 15
MAX_REVISION_ATTEMPTS = 3
# Breakeven pricing lands on zero profit by design, and rounding the price and the
# fee to cents can leave the computed profit a cent under. Treat that as breakeven,
# not as selling below cost -- a genuine below-cost target misses by far more.
BELOW_COST_TOLERANCE = 0.01
# Quantity-only revisions. The action encodes the quantity, so this needs no new column:
# mark_out_of_stock always means quantity 0, restore_stock means quantity 1.
OUT_OF_STOCK_ACTION = "mark_out_of_stock"
RESTOCK_ACTION = "restore_stock"
RETIRE_ZERO_VIEW_ACTION = "retire_zero_view"
RETIRE_DUPLICATE_ACTION = "retire_duplicate"
STOCK_ACTIONS = {OUT_OF_STOCK_ACTION, RESTOCK_ACTION, RETIRE_ZERO_VIEW_ACTION, RETIRE_DUPLICATE_ACTION}
STOCK_ACTION_QUANTITY = {
    OUT_OF_STOCK_ACTION: 0,
    RESTOCK_ACTION: 1,
    RETIRE_ZERO_VIEW_ACTION: 0,
    RETIRE_DUPLICATE_ACTION: 0,
}


def _revision_evidence(
    db: Session,
    product_id: int,
    target_price: float,
    old_price: float | None,
    listing: EbayListing | None = None,
) -> dict:
    supplier = db.scalar(
        select(SupplierProduct)
        .where(SupplierProduct.product_id == product_id)
        .order_by(SupplierProduct.created_at.asc(), SupplierProduct.id.asc())
    )
    settings = read_pricing_settings(db)
    source_price = supplier.last_price if supplier is not None else None
    source_shipping = supplier.last_shipping if supplier is not None else 0.0
    minimum_order_quantity = max(1, int(supplier.minimum_order_quantity or 1)) if supplier is not None else 1
    projected_profit = calculate_profit(
        target_price,
        source_price,
        source_shipping,
        settings,
        minimum_order_quantity,
    )["profit"]
    breakeven_mode = str(settings.get("default_pricing_strategy", "margin")) == "breakeven"
    # Breakeven pricing targets zero profit on purpose, so holding it to the normal
    # minimum-profit floor would fail every proposal and the mode could never ship.
    minimum_profit = 0.0 if breakeven_mode else float(settings.get("default_min_profit", 0.0) or 0.0)
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
    if minimum_order_quantity > 1:
        reasons.append(
            f"Source requires {minimum_order_quantity} units per order; projected cost uses {minimum_order_quantity} x ${source_price:.2f}"
            if source_price is not None
            else f"Source requires {minimum_order_quantity} units per order"
        )
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
    auto_approval_blocks: list[str] = []
    if not bool(settings.get("ebay_revision_auto_approve_enabled", False)):
        auto_approval_blocks.append("automatic approval is disabled")
    if not guard_passed:
        auto_approval_blocks.append("the pricing guard did not pass")
    if exceeds_auto_limit:
        auto_approval_blocks.append("the price change exceeds the automatic limit")
    unavailable = supplier_availability_block(supplier)
    if supplier is None:
        auto_approval_blocks.append("supplier evidence is missing")
    elif unavailable is not None:
        auto_approval_blocks.append(unavailable)
    else:
        freshness_hours = max(1.0, min(24.0, float(settings.get("source_refresh_interval_hours", 6.0) or 6.0)))
        supplier_checked_at = supplier.updated_at or supplier.created_at
        if supplier_checked_at is None or supplier_checked_at < _now() - timedelta(hours=freshness_hours):
            auto_approval_blocks.append(f"supplier evidence is older than {freshness_hours:g} hours")
        if minimum_order_quantity != 1:
            auto_approval_blocks.append("multi-unit supplier orders require manual review")
    if listing is None:
        auto_approval_blocks.append("the live listing was not revalidated")
    else:
        if str(listing.status or "").lower() not in REVISION_LISTING_STATUSES:
            auto_approval_blocks.append("the eBay listing is not active")
        if int(listing.quantity or 0) <= 0:
            auto_approval_blocks.append("the eBay listing has no sellable quantity")
        if listing.price is None or old_price is None or abs(float(listing.price) - float(old_price)) > 0.001:
            auto_approval_blocks.append("the stored live price changed during validation")
    auto_approve = not auto_approval_blocks
    if bool(settings.get("ebay_revision_auto_approve_enabled", False)) and auto_approval_blocks:
        reasons.append(f"Automatic approval withheld: {'; '.join(auto_approval_blocks)}")
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
        "auto_approval_blocks": auto_approval_blocks,
    }


def _apply_evidence(job: EbayRevisionJob, evidence: dict) -> None:
    for key, value in evidence.items():
        if key == "auto_approval_blocks":
            continue
        setattr(job, key, value)


def supplier_availability_block(supplier: SupplierProduct | None) -> str | None:
    """Why this product cannot currently be fulfilled, or None if it can be.

    Home Depot stops rendering a delivery option once an item is unavailable, and the
    capture records that as ``last_shipping = -1.0``. ``update_product_from_capture`` also
    forces -1.0 whenever a capture reports out of stock, so "the source offers no shipping"
    and "we cannot fulfil this" are the same condition rather than two separate faults.
    """
    if supplier is None:
        return None
    if supplier.in_stock is False:
        return "the supplier reports it out of stock"
    if supplier.price_unavailable:
        return "the supplier is not showing a price"
    if supplier.last_shipping is None or supplier.last_shipping < 0:
        return "the supplier is not offering a shipping option"
    return None


def _stock_job_fields(listing: EbayListing, supplier: SupplierProduct | None) -> dict:
    """Evidence for a quantity-only revision.

    These carry no pricing risk -- zeroing quantity cannot lose money and restoring it
    only returns the listing to a price that was already approved -- so they skip the
    profit guard and apply without manual approval. That is what makes the response
    automatic, which is the point of the workflow.
    """
    return {
        "source_price": supplier.last_price if supplier is not None else None,
        "source_shipping": supplier.last_shipping if supplier is not None else 0.0,
        "projected_profit": None,
        "minimum_profit": None,
        "guard_passed": True,
        "approval_required": False,
        "approved_at": _now(),
        "status": EbayRevisionJobStatus.queued.value,
    }


def enqueue_ebay_stock_revisions(
    db: Session,
    product_ids: list[int] | None = None,
) -> tuple[int, int]:
    """Zero the eBay quantity for anything the supplier can no longer fulfil, and release
    it again once the supplier recovers.

    Quantity 0 rather than ending the listing: an ended listing loses its item id, history
    and search standing, and a restock would have to be listed from scratch. Out of stock
    keeps all of it, so recovery is a single revision.
    """
    blocked = 0
    released = 0
    seen_listing_ids: set[int] = set()
    stmt = (
        select(EbayListing, SupplierProduct)
        .join(Product, Product.id == EbayListing.product_id)
        .join(SupplierProduct, SupplierProduct.product_id == Product.id)
        .where(Product.status != ProductStatus.deleted.value)
        .where(EbayListing.status.in_(REVISION_LISTING_STATUSES))
        .where(EbayListing.relist_blocked.is_(False))
        .order_by(EbayListing.created_at.desc(), EbayListing.id.desc())
    )
    if product_ids is not None:
        stmt = stmt.where(EbayListing.product_id.in_(set(product_ids)))

    for listing, supplier in db.execute(stmt).all():
        if listing.id in seen_listing_ids:
            continue
        seen_listing_ids.add(listing.id)

        reason = supplier_availability_block(supplier)
        # Decide from what AutoZS has actually applied, not from EbayListing.quantity:
        # that column defaults to 0 and is not reliably synced, so trusting it would
        # "restock" listings that were never taken down.
        last_applied = db.scalar(
            select(EbayRevisionJob)
            .where(EbayRevisionJob.ebay_listing_id == listing.id)
            .where(EbayRevisionJob.action.in_(STOCK_ACTIONS))
            .where(EbayRevisionJob.status == EbayRevisionJobStatus.completed.value)
            .order_by(EbayRevisionJob.completed_at.desc(), EbayRevisionJob.id.desc())
        )
        already_out_of_stock = last_applied is not None and last_applied.action == OUT_OF_STOCK_ACTION
        if reason is not None:
            wanted_action = None if already_out_of_stock else OUT_OF_STOCK_ACTION
        else:
            wanted_action = RESTOCK_ACTION if already_out_of_stock else None

        open_job = db.scalar(
            select(EbayRevisionJob)
            .where(EbayRevisionJob.ebay_listing_id == listing.id)
            .where(EbayRevisionJob.action.in_(STOCK_ACTIONS))
            .where(EbayRevisionJob.status.in_(ACTIVE_STATUSES))
            .order_by(EbayRevisionJob.created_at.desc(), EbayRevisionJob.id.desc())
        )
        if open_job is not None:
            if open_job.action == wanted_action or open_job.status == EbayRevisionJobStatus.running.value:
                continue
            open_job.status = EbayRevisionJobStatus.cancelled.value
            open_job.completed_at = _now()
            open_job.message = "Cancelled because supplier availability changed before this could be applied."
        if wanted_action is None:
            continue

        message = (
            f"Marking the eBay listing out of stock because {reason}."
            if wanted_action == OUT_OF_STOCK_ACTION
            else "Restoring the eBay quantity because the supplier can fulfil this again."
        )
        db.add(
            EbayRevisionJob(
                product_id=listing.product_id,
                ebay_listing_id=listing.id,
                ebay_account_key=listing.account_id or "manual",
                action=wanted_action,
                old_price=listing.price,
                # Quantity-only revision: the price is left untouched on the sheet, but the
                # column is NOT NULL so it records the price the listing already carries.
                target_price=float(listing.price) if listing.price is not None else 0.0,
                guard_reason=reason or "Supplier availability restored",
                message=message,
                **_stock_job_fields(listing, supplier),
            )
        )
        if wanted_action == OUT_OF_STOCK_ACTION:
            blocked += 1
        else:
            released += 1

    db.commit()
    return blocked, released


def enqueue_zero_view_retirement(db: Session, listing_id: int, replacement_product_id: int) -> EbayRevisionJob:
    """Queue a quantity-zero retirement only after its replacement is confirmed live."""
    listing = db.get(EbayListing, listing_id)
    if listing is None or listing.status not in REVISION_LISTING_STATUSES or int(listing.quantity or 0) <= 0:
        raise ValueError("The zero-view listing is no longer live and sellable")
    if listing.relist_blocked:
        raise ValueError("The zero-view listing is already retired")
    existing = db.scalar(
        select(EbayRevisionJob)
        .where(EbayRevisionJob.ebay_listing_id == listing.id)
        .where(EbayRevisionJob.action == RETIRE_ZERO_VIEW_ACTION)
        .where(EbayRevisionJob.status.in_(ACTIVE_STATUSES | {EbayRevisionJobStatus.completed.value}))
        .order_by(EbayRevisionJob.id.desc())
    )
    if existing is not None:
        return existing
    job = EbayRevisionJob(
        product_id=listing.product_id,
        ebay_listing_id=listing.id,
        ebay_account_key=listing.account_id or "manual",
        action=RETIRE_ZERO_VIEW_ACTION,
        old_price=listing.price,
        target_price=float(listing.price or 0),
        guard_reason=f"Zero views after the configured age; replacement product {replacement_product_id} is live.",
        message=f"Retiring zero-view listing after replacement product {replacement_product_id} was confirmed live.",
        **_stock_job_fields(listing, None),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def enqueue_duplicate_listing_retirement(
    db: Session,
    duplicate_listing_id: int,
    canonical_listing_id: int,
) -> EbayRevisionJob:
    """Queue quantity zero only when two live listings share one stable supplier SKU."""
    duplicate = db.get(EbayListing, duplicate_listing_id)
    canonical = db.get(EbayListing, canonical_listing_id)
    if duplicate is None or canonical is None or duplicate.id == canonical.id:
        raise ValueError("Duplicate and canonical listings must be distinct existing records")
    for listing in (duplicate, canonical):
        if listing.status not in REVISION_LISTING_STATUSES or int(listing.quantity or 0) <= 0:
            raise ValueError("Both duplicate candidates must be live and sellable")
    duplicate_supplier = db.scalar(select(SupplierProduct).where(SupplierProduct.product_id == duplicate.product_id))
    canonical_supplier = db.scalar(select(SupplierProduct).where(SupplierProduct.product_id == canonical.product_id))
    duplicate_sku = str(duplicate_supplier.supplier_sku or "").strip() if duplicate_supplier else ""
    canonical_sku = str(canonical_supplier.supplier_sku or "").strip() if canonical_supplier else ""
    if (
        not duplicate_sku
        or duplicate_sku != canonical_sku
        or duplicate_supplier.supplier != canonical_supplier.supplier
        or duplicate.listing_id == canonical.listing_id
    ):
        raise ValueError("Listings do not share one stable supplier identity")
    existing = db.scalar(
        select(EbayRevisionJob)
        .where(EbayRevisionJob.ebay_listing_id == duplicate.id)
        .where(EbayRevisionJob.action == RETIRE_DUPLICATE_ACTION)
        .where(EbayRevisionJob.status.in_(ACTIVE_STATUSES | {EbayRevisionJobStatus.completed.value}))
        .order_by(EbayRevisionJob.id.desc())
    )
    if existing is not None:
        return existing
    reason = (
        f"Duplicate supplier {duplicate_supplier.supplier} SKU {duplicate_sku}; preserving eBay item "
        f"{canonical.listing_id} and retiring newer item {duplicate.listing_id}."
    )
    job = EbayRevisionJob(
        product_id=duplicate.product_id,
        ebay_listing_id=duplicate.id,
        ebay_account_key=duplicate.account_id or "manual",
        action=RETIRE_DUPLICATE_ACTION,
        old_price=duplicate.price,
        target_price=float(duplicate.price or 0),
        guard_reason=reason,
        message=reason,
        **_stock_job_fields(duplicate, duplicate_supplier),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def enqueue_ebay_price_revisions(
    db: Session,
    product_ids: list[int] | None = None,
) -> tuple[int, int]:
    cancel_orphaned_ebay_revision_jobs(db, commit=False)
    # Availability is decided first. A product the supplier cannot fulfil needs its
    # quantity zeroed, not a new price, so the stock pass takes precedence and the price
    # pass below skips anything it has claimed.
    enqueue_ebay_stock_revisions(db, product_ids=product_ids)
    stmt = (
        select(EbayListing, ListingDraft)
        .join(Product, Product.id == EbayListing.product_id)
        .join(ListingDraft, ListingDraft.product_id == Product.id)
        .where(Product.status != ProductStatus.deleted.value)
        .where(EbayListing.status.in_(REVISION_LISTING_STATUSES))
        .where(EbayListing.relist_blocked.is_(False))
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
        supplier = db.scalar(
            select(SupplierProduct)
            .where(SupplierProduct.product_id == listing.product_id)
            .order_by(SupplierProduct.created_at.asc(), SupplierProduct.id.asc())
        )
        unavailable = supplier_availability_block(supplier)
        if unavailable is not None:
            # Repricing something that cannot be bought just parks a proposal in review
            # forever -- that is what left the "Supplier shipping is unknown" jobs stuck.
            active_price_job = db.scalar(
                select(EbayRevisionJob)
                .where(EbayRevisionJob.ebay_listing_id == listing.id)
                .where(EbayRevisionJob.action.not_in(STOCK_ACTIONS))
                .where(EbayRevisionJob.status.in_(ACTIVE_STATUSES - {EbayRevisionJobStatus.running.value}))
                .order_by(EbayRevisionJob.created_at.desc(), EbayRevisionJob.id.desc())
            )
            if active_price_job is not None:
                active_price_job.status = EbayRevisionJobStatus.cancelled.value
                active_price_job.completed_at = _now()
                active_price_job.message = (
                    f"Cancelled: {unavailable}, so the listing is being marked out of stock "
                    "instead of repriced."
                )
            continue
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
        evidence = _revision_evidence(db, listing.product_id, target_price, listing.price, listing)
        # Never propose selling below cost. A target whose projected profit is
        # negative is always a data fault (a stale or corrupted draft price), not a
        # pricing decision, so it must not be created or kept alive -- otherwise the
        # same loss-making proposal regenerates on every repricing pass.
        if evidence["projected_profit"] is not None and evidence["projected_profit"] < -BELOW_COST_TOLERANCE:
            if active_job is not None and active_job.status != EbayRevisionJobStatus.running.value:
                active_job.status = EbayRevisionJobStatus.cancelled.value
                active_job.completed_at = _now()
                active_job.message = (
                    f"Cancelled: target ${target_price:.2f} would sell below cost "
                    f"(projected profit ${evidence['projected_profit']:.2f})."
                )
            continue
        if active_job is not None:
            active_job.target_price = target_price
            active_job.old_price = listing.price
            _apply_evidence(active_job, evidence)
            active_job.message = (
                f"Target revalidated at ${target_price:.2f}; approved by guarded automation."
                if active_job.status == EbayRevisionJobStatus.queued.value
                else f"Target updated to ${target_price:.2f}; safety review reset."
            )
            updated += 1
            continue
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
                **{key: value for key, value in evidence.items() if key != "auto_approval_blocks"},
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
    cancel_orphaned_ebay_revision_jobs(db)
    stmt = select(EbayRevisionJob)
    if status:
        stmt = stmt.where(EbayRevisionJob.status == status)
    stmt = stmt.order_by(EbayRevisionJob.created_at.desc(), EbayRevisionJob.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def cancel_revision_jobs_for_ebay_listing(
    db: Session,
    listing: EbayListing,
    *,
    reason: str = "Cancelled because the linked eBay listing is no longer active in AutoZS.",
    commit: bool = True,
) -> int:
    cancelled = 0
    checked_at = _now()
    jobs = db.scalars(
        select(EbayRevisionJob)
        .where(EbayRevisionJob.ebay_listing_id == listing.id)
        .where(EbayRevisionJob.status.in_(ACTIVE_STATUSES))
    ).all()
    for job in jobs:
        job.status = EbayRevisionJobStatus.cancelled.value
        job.completed_at = checked_at
        job.started_at = None
        job.lease_expires_at = None
        job.message = reason
        cancelled += 1
    if cancelled and commit:
        db.commit()
    return cancelled


def cancel_orphaned_ebay_revision_jobs(db: Session, *, commit: bool = True) -> int:
    cancelled = 0
    checked_at = _now()
    rows = db.execute(
        select(EbayRevisionJob, EbayListing)
        .join(EbayListing, EbayListing.id == EbayRevisionJob.ebay_listing_id, isouter=True)
        .where(EbayRevisionJob.status.in_(ACTIVE_STATUSES))
    ).all()
    for job, listing in rows:
        listing_status = str(listing.status or "").lower() if listing is not None else ""
        if listing is not None and listing_status in REVISION_LISTING_STATUSES:
            continue
        if listing is None:
            reason = "Cancelled because the linked eBay listing record is missing from AutoZS."
        elif listing_status in TERMINAL_REVISION_LISTING_STATUSES or listing_status not in REVISION_LISTING_STATUSES:
            reason = f"Cancelled because the linked eBay listing is {listing_status or 'not active'} in AutoZS."
        else:
            continue
        job.status = EbayRevisionJobStatus.cancelled.value
        job.completed_at = checked_at
        job.started_at = None
        job.lease_expires_at = None
        job.message = reason
        cancelled += 1
    if cancelled and commit:
        db.commit()
    return cancelled


def create_ebay_revision_canary(
    db: Session,
    *,
    product_id: int,
    target_price: float,
    reason: str,
) -> EbayRevisionJob:
    listing = db.scalar(
        select(EbayListing)
        .where(EbayListing.product_id == product_id, EbayListing.status.in_(REVISION_LISTING_STATUSES))
        .order_by(EbayListing.created_at.desc(), EbayListing.id.desc())
    )
    if listing is None:
        raise ValueError("Canary revisions require a scheduled or live eBay listing")
    target = round(float(target_price), 2)
    current = round(float(listing.price), 2) if listing.price is not None else None
    if current == target:
        raise ValueError("The canary target already matches the stored eBay price")
    evidence = _revision_evidence(db, product_id, target, listing.price, listing)
    if not evidence["guard_passed"]:
        raise ValueError(evidence["guard_reason"])
    for existing in db.scalars(
        select(EbayRevisionJob).where(
            EbayRevisionJob.ebay_listing_id == listing.id,
            EbayRevisionJob.status.in_(ACTIVE_STATUSES),
        )
    ).all():
        existing.status = EbayRevisionJobStatus.cancelled.value
        existing.completed_at = _now()
        existing.lease_expires_at = None
        existing.message = "Superseded by a controlled price-revision canary."
    job = EbayRevisionJob(
        product_id=product_id,
        ebay_listing_id=listing.id,
        ebay_account_key=listing.account_id or "manual",
        old_price=listing.price,
        target_price=target,
        source_price=evidence["source_price"],
        source_shipping=evidence["source_shipping"],
        projected_profit=evidence["projected_profit"],
        minimum_profit=evidence["minimum_profit"],
        guard_passed=True,
        guard_reason=f"{evidence['guard_reason']}; {reason.strip() or 'controlled canary'}",
        approval_required=True,
        approved_at=None,
        status=EbayRevisionJobStatus.needs_review.value,
        message=f"Canary proposes {_price(listing.price)} → ${target:.2f}; manual approval required.",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


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
            EbayRevisionJobStatus.paused.value,
        }:
            job.lease_expires_at = None
        if status in {
            EbayRevisionJobStatus.completed.value,
            EbayRevisionJobStatus.failed.value,
            EbayRevisionJobStatus.cancelled.value,
        }:
            job.completed_at = _now()
        if status == EbayRevisionJobStatus.queued.value:
            job.started_at = None
            job.completed_at = None
            job.lease_expires_at = None
        if status == EbayRevisionJobStatus.completed.value:
            listing = db.get(EbayListing, job.ebay_listing_id)
            if listing is not None:
                if job.action in STOCK_ACTION_QUANTITY:
                    listing.quantity = STOCK_ACTION_QUANTITY[job.action]
                    if job.action in {RETIRE_ZERO_VIEW_ACTION, RETIRE_DUPLICATE_ACTION}:
                        listing.relist_blocked = True
                        listing.removal_reason = (
                            "duplicate_supplier_listing"
                            if job.action == RETIRE_DUPLICATE_ACTION
                            else "zero_views_29_days"
                        )
                        listing.removal_detail = job.guard_reason
                        listing.removed_at = _now()
                        if job.action == RETIRE_DUPLICATE_ACTION:
                            sibling_rows = (
                                db.query(EbayListing)
                                .filter(
                                    EbayListing.listing_id == listing.listing_id,
                                    EbayListing.id != listing.id,
                                )
                                .all()
                            )
                            for sibling in sibling_rows:
                                sibling.quantity = 0
                                sibling.status = "tombstoned"
                                sibling.relist_blocked = True
                                sibling.removal_reason = "duplicate_supplier_listing"
                                sibling.removal_detail = job.guard_reason
                                sibling.removed_at = listing.removed_at
                else:
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
    supplier = db.scalar(
        select(SupplierProduct)
        .where(SupplierProduct.product_id == job.product_id)
        .order_by(SupplierProduct.created_at.asc(), SupplierProduct.id.asc())
    )
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
        "old_source_price": _revision_old_source_price(db, job),
        "source_price": job.source_price,
        "minimum_order_quantity": max(1, int(supplier.minimum_order_quantity or 1)) if supplier is not None else 1,
        "source_order_subtotal": (
            round(float(job.source_price) * max(1, int(supplier.minimum_order_quantity or 1)), 2)
            if job.source_price is not None and supplier is not None
            else job.source_price
        ),
        "source_shipping": job.source_shipping,
        "source_url": supplier.source_url if supplier is not None else None,
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


def _revision_old_source_price(db: Session, job: EbayRevisionJob) -> float | None:
    """Return the source price that immediately preceded this revision's evidence.

    Source refresh jobs retain the authoritative baseline/captured pair. Revision
    jobs historically stored only the captured price, so use the latest matching
    changed refresh to provide a real before value for existing and future cards.
    Revisions created by a pricing-only recalculation have no source-price change;
    in that case the before and after values are intentionally identical.
    """
    if job.source_price is None:
        return None
    refresh = db.scalar(
        select(SourceRefreshJob)
        .where(
            SourceRefreshJob.product_id == job.product_id,
            SourceRefreshJob.status == SourceRefreshJobStatus.completed.value,
            SourceRefreshJob.price_changed.is_(True),
            SourceRefreshJob.captured_price == job.source_price,
            SourceRefreshJob.completed_at.is_not(None),
            SourceRefreshJob.completed_at <= job.updated_at,
        )
        .order_by(SourceRefreshJob.completed_at.desc(), SourceRefreshJob.id.desc())
    )
    if refresh is not None and refresh.baseline_price is not None:
        return refresh.baseline_price
    return job.source_price


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

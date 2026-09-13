import json
import math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from app.core.config import PROJECT_ROOT
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.depop import DepopAccount, DepopListingJob, DepopListingVariant, DepopSourcePhoto
from app.models.domain import Product, ProductImage


def _now_utc_naive() -> datetime:
    return datetime.utcnow()


def depop_shipping(variant: DepopListingVariant) -> dict:
    packed = variant.packed_weight_lb
    supplier = variant.supplier_weight_lb
    for value in (packed, supplier):
        if value is not None and (not math.isfinite(value) or value <= 0):
            return {"shipping_method": "", "shipping_weight_lb": None, "shipping_weight_source": "invalid"}
    weight = packed if packed is not None else 2.0
    source = "packed_weight" if packed is not None else "owner_approved_estimate"
    if supplier is not None and supplier > weight:
        weight, source = supplier, "supplier_weight"
    tiers = [(0.25, "Extra extra small Under 4oz"), (0.5, "Extra small Under 8oz"),
             (0.75, "Small Under 12oz"), (1.0, "Medium Under 1lb"),
             (2.0, "Large Under 2lb"), (10.0, "Extra large Under 10lb")]
    required = next((index for index, (limit, _) in enumerate(tiers) if weight < limit), None)
    explicit = next((index for index, (_, name) in enumerate(tiers)
                     if name.replace(" ", "").lower() == variant.shipping_method.replace(" ", "").lower()), None)
    method = "" if required is None else tiers[max(required, explicit if explicit is not None else required)][1]
    return {"shipping_method": method, "shipping_weight_lb": weight, "shipping_weight_source": source}


def build_depop_listing_package(db: Session, variant: DepopListingVariant) -> dict | None:
    product = db.get(Product, variant.product_id)
    if product is None:
        return None
    try:
        image_ids = json.loads(variant.image_ids_json or "[]")
        if not isinstance(image_ids, list) or any(type(value) is not int for value in image_ids):
            image_ids = []
    except (ValueError, TypeError):
        image_ids = []
    images_by_id = {
        image.id: image
        for image in db.scalars(select(ProductImage).where(ProductImage.id.in_(image_ids), ProductImage.product_id == variant.product_id)).all()
    } if image_ids else {}
    # Preserve the curated order rather than whatever order the DB returns rows in.
    ordered_images = [images_by_id[image_id] for image_id in image_ids if image_id in images_by_id]
    return {
        "variant_id": variant.id,
        "product_id": variant.product_id,
        "account_key": variant.account_key,
        "sku": product.sku,
        "title": variant.title,
        "description": variant.description,
        "price": variant.price,
        "image_urls": [image.image_url for image in ordered_images],
        # depop-fill.js uploads these downloaded copies (served off the local
        # API, same as eBay's manual_image_paths) instead of fetching the
        # original supplier URL directly from depop.com, which CORS blocks.
        "local_image_paths": [image.local_path for image in ordered_images if image.local_path],
        "size": variant.size,
        "brand": variant.brand,
        "category": variant.category,
        "condition": variant.condition,
        "color": variant.color,
        **depop_shipping(variant),
    }


def serialize_depop_job(db: Session, job: DepopListingJob) -> dict:
    base = {
        "id": job.id,
        "variant_id": job.variant_id,
        "account_key": job.account_key,
        "action": job.action,
        "status": job.status,
        "scheduled_for": job.scheduled_for,
        "attempts": job.attempts,
        "progress": job.progress,
        "message": job.message,
        "runner_url": job.runner_url,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
    variant = db.get(DepopListingVariant, job.variant_id)
    package = build_depop_listing_package(db, variant) if variant else None
    if package is None:
        return {
            **base,
            "product_id": None,
            "sku": "missing",
            "title": "Missing Depop variant",
            "depop_listing_id": None,
        }
    return {
        **base,
        "product_id": package["product_id"],
        "sku": package["sku"],
        "title": package["title"],
        "description": package["description"],
        "price": package["price"],
        "image_urls": package["image_urls"],
        "local_image_paths": package["local_image_paths"],
        "size": package["size"],
        "brand": package["brand"],
        "category": package["category"],
        "condition": package["condition"],
        "color": package["color"],
        "shipping_method": package["shipping_method"],
        "shipping_weight_lb": package["shipping_weight_lb"],
        "shipping_weight_source": package["shipping_weight_source"],
        "depop_listing_id": variant.depop_listing_id,
    }


def depop_runner_url(job_id: int, account_key: str) -> str:
    params = {
        "autozs_fill": "1",
        "autozs_job_id": str(job_id),
        "autozs_account_key": account_key or "manual",
    }
    return f"https://www.depop.com/products/create/?{urlencode(params)}"


def lock_depop_queue(db: Session) -> None:
    # SQLite serializes writers; PostgreSQL locks the account rows. Acquire
    # before reading queue state so concurrent pollers/enrollers cannot race.
    db.execute(update(DepopAccount).values(
        enabled=DepopAccount.enabled, updated_at=DepopAccount.updated_at,
    ))


def depop_listing_problem(db: Session, variant: DepopListingVariant) -> str | None:
    package = build_depop_listing_package(db, variant)
    if package is None or not math.isfinite(variant.price) or variant.price <= 0:
        return "Depop listing needs a positive finite price and an existing product."
    if any(not getattr(variant, field).strip() for field in ("title", "description", "brand", "category", "condition")):
        return "Depop listing needs a title, description, brand, category, condition, and shipping method."
    if not package["shipping_method"]:
        return "Depop listing weight does not fit a supported shipping tier."
    try:
        selected = json.loads(variant.image_ids_json or "[]")
        valid_selection = isinstance(selected, list) and len(set(selected)) == len(selected) == len(package["image_urls"])
    except (ValueError, TypeError):
        valid_selection = False
    if not valid_selection:
        return "Every selected Depop image must be unique and belong to this product."
    if len(package["image_urls"]) not in (3, 4) or len(package["local_image_paths"]) != len(package["image_urls"]):
        return "Depop listing needs 3 or 4 downloaded product images."
    root = (PROJECT_ROOT / "downloads").resolve()
    for value in package["local_image_paths"]:
        path = (PROJECT_ROOT / value.lstrip("/\\")).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return "Depop listing image file is missing or outside the downloads folder."
    return None


def start_next_depop_job(db: Session, now: datetime | None = None, account_key: str | None = None) -> DepopListingJob | None:
    """Claim the oldest due queued job for the extension's single dedicated
    Depop Chrome profile. Only one job may run at a time -- there is one
    browser profile, so a second concurrent runner would just fight the first
    one over the same tab."""
    lock_depop_queue(db)
    now = now or _now_utc_naive()
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    if db.scalar(select(DepopListingJob).where(DepopListingJob.status == "running")) is not None:
        return None
    stmt = (
        select(DepopListingJob)
        .where(DepopListingJob.status == "queued")
        .where(or_(DepopListingJob.scheduled_for.is_(None), DepopListingJob.scheduled_for <= now))
        .order_by(DepopListingJob.scheduled_for.asc().nullsfirst(), DepopListingJob.created_at.asc(), DepopListingJob.id.asc())
    )
    if account_key is not None:
        stmt = stmt.where(DepopListingJob.account_key == account_key)
    job = db.scalar(stmt)
    if job is None:
        return None
    variant = db.get(DepopListingVariant, job.variant_id)
    account = db.scalar(select(DepopAccount).where(DepopAccount.key == job.account_key))
    if variant is None or account is None or not account.enabled or not account.writes_enabled:
        job.status = "needs_review"
        job.message = "Depop account is unavailable or browser writes are disabled."
        db.commit()
        db.refresh(job)
        return job
    if (variant.account_key != job.account_key or job.action != "create"
            or variant.depop_listing_id or variant.status in {"published", "active"}):
        job.status = "needs_review"
        job.message = "Depop job account/action changed or the variant is already published."
        db.commit()
        db.refresh(job)
        return job
    problem = depop_listing_problem(db, variant)
    if problem:
        job.status = "needs_review"
        job.message = problem
        db.commit()
        db.refresh(job)
        return job
    job.status = "running"
    job.attempts += 1
    job.progress = 0
    job.message = "Reserved for Depop listing creation."
    job.runner_url = depop_runner_url(job.id, job.account_key)
    db.commit()
    db.refresh(job)
    return job


def _next_schedule_slots(now_utc: datetime, timezone_name: str, hours: list[int]):
    try:
        local_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc
    normalized_hours = sorted(set(int(hour) for hour in hours))
    if not normalized_hours or any(hour < 0 or hour > 23 for hour in normalized_hours):
        raise ValueError("Daily schedule hours must be between 0 and 23.")
    aware_now = now_utc.replace(tzinfo=timezone.utc) if now_utc.tzinfo is None else now_utc.astimezone(timezone.utc)
    local_now = aware_now.astimezone(local_zone)
    day = local_now.date()
    while True:
        for hour in normalized_hours:
            local_slot = datetime(day.year, day.month, day.day, hour, tzinfo=local_zone)
            utc_slot = local_slot.astimezone(timezone.utc)
            # A nonexistent spring-forward wall hour must not silently shift.
            if utc_slot.astimezone(local_zone).replace(tzinfo=None) != local_slot.replace(tzinfo=None):
                continue
            if utc_slot > aware_now:
                yield utc_slot.replace(tzinfo=None)
        day += timedelta(days=1)


def schedule_approved_photo_batches(
    db: Session,
    *,
    account_key: str,
    timezone_name: str = "America/Chicago",
    daily_hours: list[int] | None = None,
    now: datetime | None = None,
) -> tuple[list[DepopListingJob], int, int, int]:
    """Turn every complete group of four approved photos into an idempotent
    listing variant and queue it at the next noon/evening slot."""
    lock_depop_queue(db)
    account = db.scalar(select(DepopAccount).where(DepopAccount.key == account_key))
    if account is None or not account.enabled or not account.writes_enabled:
        raise ValueError("Depop account is unavailable or browser writes are disabled.")

    base_variants = list(db.scalars(
        select(DepopListingVariant)
        .where(DepopListingVariant.account_key == account_key)
        .where(~DepopListingVariant.variant_key.contains("::batch-"))
        .order_by(DepopListingVariant.product_id, DepopListingVariant.id)
    ).all())
    slot_iter = _next_schedule_slots(now or _now_utc_naive(), timezone_name, daily_hours if daily_hours is not None else list(range(0, 24, 2)))
    occupied_slots = {
        job.scheduled_for
        for job in db.scalars(select(DepopListingJob).where(
            DepopListingJob.account_key == account_key, DepopListingJob.status != "cancelled",
        )).all()
        if job.scheduled_for is not None
    }

    def next_free_slot() -> datetime:
        for candidate in slot_iter:
            if candidate not in occupied_slots:
                occupied_slots.add(candidate)
                return candidate

    jobs: list[DepopListingJob] = []
    created = used = remaining = 0

    for base in base_variants:
        photos = list(db.scalars(
            select(DepopSourcePhoto)
            .where(DepopSourcePhoto.variant_id == base.id, DepopSourcePhoto.status == "approved")
            .order_by(DepopSourcePhoto.sort_order, DepopSourcePhoto.id)
        ).all())
        complete_count = len(photos) // 4
        remaining += len(photos) % 4
        for batch_index in range(1, complete_count + 1):
            batch = photos[(batch_index - 1) * 4:batch_index * 4]
            urls = [photo.image_url for photo in batch]
            images = list(db.scalars(
                select(ProductImage).where(
                    ProductImage.product_id == base.product_id,
                    ProductImage.image_url.in_(urls),
                )
            ).all())
            by_url = {image.image_url: image for image in images}
            if any(url not in by_url for url in urls):
                remaining += 4
                continue
            image_ids = [by_url[url].id for url in urls]
            variant = base if batch_index == 1 else db.scalar(select(DepopListingVariant).where(
                DepopListingVariant.product_id == base.product_id,
                DepopListingVariant.variant_key == f"{base.variant_key}::batch-{batch_index}",
            ))
            if variant is not None and variant.depop_listing_id:
                used += 4
                continue
            if variant is not None:
                existing = db.scalar(select(DepopListingJob).where(
                    DepopListingJob.variant_id == variant.id,
                    or_(DepopListingJob.status != "cancelled", DepopListingJob.attempts > 0),
                ))
                if existing is not None:
                    used += 4
                    continue
            if batch_index > 1 and variant is None:
                variant = DepopListingVariant(
                    product_id=base.product_id,
                    account_key=base.account_key,
                    variant_key=f"{base.variant_key}::batch-{batch_index}",
                    title=base.title,
                    description=base.description,
                    price=base.price,
                    image_ids_json=json.dumps(image_ids),
                    size=base.size,
                    brand=base.brand or "Other",
                    category=base.category or "Bags",
                    condition=base.condition or "Brand new",
                    color=base.color,
                    shipping_method=base.shipping_method,
                    packed_weight_lb=base.packed_weight_lb,
                    supplier_weight_lb=base.supplier_weight_lb,
                    status="ready",
                )
                db.add(variant)
                db.flush()
                created += 1
            else:
                variant.image_ids_json = json.dumps(image_ids)
                variant.brand = variant.brand or "Other"
                variant.category = variant.category or "Bags"
                variant.condition = variant.condition or "Brand new"
                variant.status = "ready"
            problem = depop_listing_problem(db, variant)
            if problem:
                raise ValueError(problem)
            job = DepopListingJob(
                variant_id=variant.id,
                account_key=variant.account_key,
                action="create",
                status="queued",
                scheduled_for=next_free_slot(),
                message="Scheduled from an approved four-photo batch.",
            )
            variant.status = "queued"
            db.add(job)
            db.flush()
            jobs.append(job)
            used += 4
    db.commit()
    for job in jobs:
        db.refresh(job)
    return jobs, created, used, remaining

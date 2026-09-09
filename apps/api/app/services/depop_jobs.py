import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.depop import DepopAccount, DepopListingJob, DepopListingVariant, DepopSourcePhoto
from app.models.domain import Product, ProductImage


def _now_utc_naive() -> datetime:
    return datetime.utcnow()


def build_depop_listing_package(db: Session, variant: DepopListingVariant) -> dict | None:
    product = db.get(Product, variant.product_id)
    if product is None:
        return None
    image_ids = json.loads(variant.image_ids_json or "[]")
    images_by_id = {
        image.id: image
        for image in db.scalars(select(ProductImage).where(ProductImage.id.in_(image_ids))).all()
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
        # Current purse inventory weighs about 0.36 kg / 12.7 oz. Depop's
        # matching USPS tier is Medium (under 1 lb).
        "shipping_method": "Medium Under 1lb" if variant.category.lower() == "bags" else "",
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
        "depop_listing_id": variant.depop_listing_id,
    }


def depop_runner_url(job_id: int, account_key: str) -> str:
    params = {
        "autozs_fill": "1",
        "autozs_job_id": str(job_id),
        "autozs_account_key": account_key or "manual",
    }
    return f"https://www.depop.com/products/create/?{urlencode(params)}"


def start_next_depop_job(db: Session, now: datetime | None = None) -> DepopListingJob | None:
    """Claim the oldest due queued job for the extension's single dedicated
    Depop Chrome profile. Only one job may run at a time -- there is one
    browser profile, so a second concurrent runner would just fight the first
    one over the same tab."""
    now = now or _now_utc_naive()
    if db.scalar(select(DepopListingJob).where(DepopListingJob.status == "running")) is not None:
        return None
    stmt = (
        select(DepopListingJob)
        .where(DepopListingJob.status == "queued")
        .where(or_(DepopListingJob.scheduled_for.is_(None), DepopListingJob.scheduled_for <= now))
        .order_by(DepopListingJob.scheduled_for.asc().nullsfirst(), DepopListingJob.created_at.asc(), DepopListingJob.id.asc())
    )
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
    job.status = "running"
    job.attempts += 1
    job.progress = 0
    job.message = "Reserved for Depop listing creation."
    job.runner_url = depop_runner_url(job.id, job.account_key)
    db.commit()
    db.refresh(job)
    return job


def _listing_description(variant: DepopListingVariant) -> str:
    if variant.description.strip():
        return variant.description.strip()
    color = variant.color.strip() or "This"
    return (
        f"{color} handbag with multiple pockets and a comfortable shoulder/crossbody design. "
        "A practical everyday bag for travel, work, and casual use. Brand new condition."
    )


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
            if local_slot > local_now:
                yield local_slot.astimezone(timezone.utc).replace(tzinfo=None)
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
    account = db.scalar(select(DepopAccount).where(DepopAccount.key == account_key))
    if account is None or not account.enabled or not account.writes_enabled:
        raise ValueError("Depop account is unavailable or browser writes are disabled.")

    base_variants = list(db.scalars(
        select(DepopListingVariant)
        .where(DepopListingVariant.account_key == account_key)
        .where(~DepopListingVariant.variant_key.contains("::batch-"))
        .order_by(DepopListingVariant.product_id, DepopListingVariant.id)
    ).all())
    slot_iter = _next_schedule_slots(now or _now_utc_naive(), timezone_name, daily_hours or [12, 20])
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
            if batch_index > 1 and variant is None:
                variant = DepopListingVariant(
                    product_id=base.product_id,
                    account_key=base.account_key,
                    variant_key=f"{base.variant_key}::batch-{batch_index}",
                    title=base.title,
                    description=_listing_description(base),
                    price=base.price,
                    image_ids_json=json.dumps(image_ids),
                    size=base.size,
                    brand=base.brand or "Other",
                    category=base.category or "Bags",
                    condition=base.condition or "Brand new",
                    color=base.color,
                    status="ready",
                )
                db.add(variant)
                db.flush()
                created += 1
            elif variant is not None and not variant.depop_listing_id:
                variant.image_ids_json = json.dumps(image_ids)
                variant.description = _listing_description(variant)
                variant.brand = variant.brand or "Other"
                variant.category = variant.category or "Bags"
                variant.condition = variant.condition or "Brand new"
                variant.status = "ready"
            if variant is None or variant.depop_listing_id:
                used += 4
                continue
            existing = db.scalar(select(DepopListingJob).where(
                DepopListingJob.variant_id == variant.id,
                DepopListingJob.status.in_(["queued", "running", "completed"]),
            ))
            if existing is not None:
                used += 4
                continue
            job = DepopListingJob(
                variant_id=variant.id,
                account_key=variant.account_key,
                action="create",
                status="queued",
                scheduled_for=next(slot_iter),
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

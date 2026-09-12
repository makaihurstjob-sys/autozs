"""Leased, opt-in prelisting checks; supplier access is exclusively through Chrome."""
from datetime import datetime, timedelta
import json
from uuid import uuid4

from sqlalchemy import select, update, or_
from sqlalchemy.orm import Session

from app.models.domain import AppSetting, DeliveryCheckJob, EbayListing, ListingJob, Product, SupplierProduct
from app.services.delivery_quotes import home_depot_item_id, record_cart_quote

POLICY_KEY = "delivery_check_policy"
DEFAULT_POLICY = {"enabled": False, "postal_codes": ["10001", "33101", "60601", "75201", "90001"], "trial": None}
MAX_ATTEMPTS = 3
FRESH_HOURS = 24
LEASE_MINUTES = 10


def read_policy(db: Session) -> dict:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == POLICY_KEY))
    return {**DEFAULT_POLICY, **(json.loads(setting.value) if setting else {})}


def write_policy(db: Session, policy: dict) -> dict:
    previous = read_policy(db)
    trial = policy.get("trial")
    if trial:
        if policy["enabled"]:
            raise ValueError("Disable broad checks before configuring a bounded trial")
        supplier = db.get(SupplierProduct, trial["supplier_product_id"])
        product = db.get(Product, supplier.product_id) if supplier else None
        if not product or product.status not in {"draft", "monitoring"} or not home_depot_item_id(supplier.source_url):
            raise ValueError("Trial requires an eligible Home Depot supplier product")
    # Revocation is durable: toggling back cannot resurrect a browser lease.
    for job in db.scalars(select(DeliveryCheckJob).where(DeliveryCheckJob.status == "running")).all():
        if not in_scope(policy, job.supplier_product_id, job.postal_code) or (
                previous.get("trial") != trial and previous.get("trial")):
            job.status, job.lease_token, job.lease_expires_at = "needs_review", "", None
            job.message = "Delivery scope changed; inspect isolated cart before retrying"
    setting = db.scalar(select(AppSetting).where(AppSetting.key == POLICY_KEY))
    if setting is None:
        setting = AppSetting(key=POLICY_KEY)
        db.add(setting)
    setting.value = json.dumps(policy)
    db.commit()
    return read_policy(db)


def in_scope(policy: dict, supplier_id: int, postal_code: str) -> bool:
    trial = policy.get("trial")
    if trial:
        return supplier_id == trial["supplier_product_id"] and postal_code == trial["postal_code"]
    return policy["enabled"] and postal_code in policy["postal_codes"]


def coverage_reason(db: Session, product_id: int) -> str | None:
    policy = read_policy(db)
    if not policy["enabled"]:
        return None
    product = db.get(Product, product_id)
    supplier = product.supplier_products[0] if product and product.supplier_products else None
    if not supplier or not home_depot_item_id(supplier.source_url):
        return None
    cutoff = datetime.utcnow() - timedelta(hours=FRESH_HOURS)
    jobs = {j.postal_code: j for j in db.scalars(select(DeliveryCheckJob).where(
        DeliveryCheckJob.supplier_product_id == supplier.id)).all()}
    missing = []
    for zip_code in policy["postal_codes"]:
        job = jobs.get(zip_code)
        if not (job and job.status == "completed" and job.completed_at and job.completed_at >= cutoff
                and job.delivery_charge == 0 and home_depot_item_id(job.source_url) == home_depot_item_id(supplier.source_url)):
            missing.append(zip_code)
    if missing:
        return "Delivery checks pending or need review for ZIPs " + ", ".join(missing) + "."
    return None


def ensure_checks(db: Session, product_id: int) -> list[DeliveryCheckJob]:
    policy = read_policy(db)
    if not policy["enabled"] and not policy.get("trial"):
        return []
    product = db.get(Product, product_id)
    trial = policy.get("trial")
    supplier = (db.get(SupplierProduct, trial["supplier_product_id"]) if trial
                else product.supplier_products[0] if product and product.supplier_products else None)
    if (not product or not supplier or supplier.product_id != product_id
            or product.status not in {"draft", "monitoring"} or not home_depot_item_id(supplier.source_url)):
        return []
    result = []
    for zip_code in ([trial["postal_code"]] if trial else policy["postal_codes"]):
        job = db.scalar(select(DeliveryCheckJob).where(
            DeliveryCheckJob.supplier_product_id == supplier.id, DeliveryCheckJob.postal_code == zip_code))
        if job is None:
            job = DeliveryCheckJob(supplier_product_id=supplier.id, postal_code=zip_code, source_url=supplier.source_url)
            db.add(job)
        elif job.status == "completed" and (not job.completed_at
                or job.completed_at < datetime.utcnow() - timedelta(hours=FRESH_HOURS)
                or home_depot_item_id(job.source_url) != home_depot_item_id(supplier.source_url)):
            # A concurrent enrollment may already have requeued this completion,
            # and a browser may now own it. Never flush a stale ORM snapshot over
            # that lease (or over a newer completion).
            db.execute(update(DeliveryCheckJob).where(
                DeliveryCheckJob.id == job.id,
                DeliveryCheckJob.status == "completed",
                DeliveryCheckJob.completed_at == job.completed_at,
                DeliveryCheckJob.source_url == job.source_url,
            ).values(status="queued", attempts=0, source_url=supplier.source_url,
                     completed_at=None, delivery_charge=None, retry_at=None,
                     lease_token="", lease_expires_at=None,
                     message="Delivery evidence expired or supplier product changed"),
                execution_options={"synchronize_session": False})
            db.refresh(job)
        result.append(job)
    db.commit()
    return result


def enroll_live_listings(db: Session, account_id: str, listing_ids: list[int]) -> dict:
    """Explicit bounded audit; supplier/ZIP evidence is shared, listing selection is not."""
    policy = read_policy(db)
    if not policy["enabled"] or policy.get("trial"):
        raise ValueError("Enable configured ZIP checks before enrolling live listings")
    if (not account_id.strip() or not 1 <= len(listing_ids) <= 100
            or any(type(value) is not int or value <= 0 for value in listing_ids)
            or len(set(listing_ids)) != len(listing_ids)):
        raise ValueError("Provide an account and 1 to 100 unique listing row IDs")
    listings = {row.id: row for row in db.scalars(select(EbayListing).where(
        EbayListing.id.in_(listing_ids), EbayListing.account_id == account_id,
        EbayListing.environment == "production", EbayListing.status.in_({"active", "live", "listed"}),
    )).all()}
    enrolled, skipped = [], []
    for listing_id in listing_ids:
        listing = listings.get(listing_id)
        if listing is None:
            skipped.append({"listing_id": listing_id, "reason": "No active production listing in this account"})
            continue
        jobs = ensure_checks(db, listing.product_id)
        if not jobs:
            skipped.append({"listing_id": listing_id, "reason": "Product is not eligible for Home Depot checks"})
            continue
        enrolled.append({"listing_id": listing_id, "product_id": listing.product_id,
                         "jobs": [serialize_job(job) for job in jobs]})
    return {"account_id": account_id, "postal_codes": policy["postal_codes"],
            "enrolled": enrolled, "skipped": skipped}


def serialize_job(job: DeliveryCheckJob) -> dict:
    return {key: getattr(job, key) for key in (
        "id", "supplier_product_id", "postal_code", "source_url", "status", "attempts",
        "lease_expires_at", "retry_at", "completed_at", "delivery_charge", "message")}


def claim_check(db: Session, worker_id: str) -> dict | None:
    policy = read_policy(db)
    if not policy["enabled"] and not policy.get("trial"):
        return None
    # Old listing jobs are enrolled as well as new enqueue requests.
    product_ids = db.scalars(select(ListingJob.product_id).where(
        ListingJob.status.in_({"queued", "needs_review", "paused"})).distinct()).all()
    if policy.get("trial"):
        supplier = db.get(SupplierProduct, policy["trial"]["supplier_product_id"])
        product_ids = [supplier.product_id] if supplier else []
    for product_id in product_ids:
        ensure_checks(db, product_id)
    now = datetime.utcnow()
    expired = db.scalars(select(DeliveryCheckJob).where(
        DeliveryCheckJob.status == "running", DeliveryCheckJob.lease_expires_at <= now)).all()
    for job in expired:
        job.status = "needs_review" if job.attempts >= MAX_ATTEMPTS else "queued"
        job.retry_at = now + timedelta(minutes=5)
        job.lease_token = ""
        job.message = "Browser lease expired; inspect any leftover cart before retrying"
    db.commit()
    active = db.scalar(select(DeliveryCheckJob).where(
        DeliveryCheckJob.status == "running", DeliveryCheckJob.worker_id == worker_id))
    if active:
        try:
            validate_active_check(db, active)
        except ValueError:
            return None
        return {**serialize_job(active), "lease_token": active.lease_token}
    candidates = db.scalars(select(DeliveryCheckJob).where(
        DeliveryCheckJob.status == "queued", DeliveryCheckJob.attempts < MAX_ATTEMPTS,
        or_(DeliveryCheckJob.retry_at.is_(None), DeliveryCheckJob.retry_at <= now),
    ).order_by(DeliveryCheckJob.updated_at, DeliveryCheckJob.id)).all()
    for job in candidates:
        if not in_scope(policy, job.supplier_product_id, job.postal_code):
            continue
        supplier = db.get(SupplierProduct, job.supplier_product_id)
        product = db.get(Product, supplier.product_id) if supplier else None
        if not product or product.status not in {"draft", "monitoring"} or not home_depot_item_id(supplier.source_url):
            continue
        token = uuid4().hex
        changed = db.execute(update(DeliveryCheckJob).where(
            DeliveryCheckJob.id == job.id, DeliveryCheckJob.status == "queued",
        ).values(status="running", attempts=DeliveryCheckJob.attempts + 1,
                 source_url=supplier.source_url, worker_id=worker_id, lease_token=token,
                 lease_expires_at=now + timedelta(minutes=LEASE_MINUTES), message="Checking guest cart"))
        db.commit()
        if changed.rowcount:
            db.refresh(job)
            return {**serialize_job(job), "lease_token": token}
    return None


def owned_job(db: Session, job_id: int, worker_id: str, lease_token: str) -> DeliveryCheckJob:
    job = db.get(DeliveryCheckJob, job_id)
    if not (job and job.status == "running" and job.worker_id == worker_id
            and job.lease_token == lease_token and job.lease_expires_at and job.lease_expires_at > datetime.utcnow()):
        raise ValueError("Delivery check lease expired or belongs to another worker")
    return job


def validate_active_check(db: Session, job: DeliveryCheckJob) -> None:
    policy = read_policy(db)
    if not in_scope(policy, job.supplier_product_id, job.postal_code):
        raise ValueError("Delivery checks paused or ZIP no longer configured")
    supplier = db.get(SupplierProduct, job.supplier_product_id)
    if (not supplier or not home_depot_item_id(job.source_url)
            or home_depot_item_id(supplier.source_url) != home_depot_item_id(job.source_url)):
        raise ValueError("Delivery check supplier product changed")


def heartbeat(db: Session, job_id: int, worker_id: str, lease_token: str) -> dict:
    existing = db.get(DeliveryCheckJob, job_id)
    if (existing and existing.status == "completed" and existing.worker_id == worker_id
            and existing.lease_token == lease_token):
        return serialize_job(existing)
    job = owned_job(db, job_id, worker_id, lease_token)
    validate_active_check(db, job)
    job.lease_expires_at = datetime.utcnow() + timedelta(minutes=LEASE_MINUTES)
    db.commit()
    return serialize_job(job)


def finish_check(db: Session, job_id: int, worker_id: str, lease_token: str, quote: dict) -> dict:
    job = owned_job(db, job_id, worker_id, lease_token)
    validate_active_check(db, job)
    supplier = db.get(SupplierProduct, job.supplier_product_id)
    if (not supplier or home_depot_item_id(quote["source_url"]) != home_depot_item_id(job.source_url)
            or home_depot_item_id(supplier.source_url) != home_depot_item_id(job.source_url)
            or quote["postal_code"] != job.postal_code or quote["quantity"] != 1):
        raise ValueError("Cart evidence does not match the leased product, ZIP and quantity")
    # Commit the quote and completion together, so a lost response can be inspected.
    job.status, job.completed_at = "completed", datetime.utcnow()
    job.delivery_charge, job.message = quote["delivery_charge"], "Guest cart checked and cleared"
    job.lease_expires_at = None
    record_cart_quote(db, **quote)
    return serialize_job(job)


def fail_check(db: Session, job_id: int, worker_id: str, lease_token: str, message: str, retryable: bool) -> dict:
    job = owned_job(db, job_id, worker_id, lease_token)
    job.status = "queued" if retryable and job.attempts < MAX_ATTEMPTS else "needs_review"
    job.retry_at = datetime.utcnow() + timedelta(minutes=5)
    job.lease_expires_at, job.lease_token = None, ""
    job.message = message
    db.commit()
    return serialize_job(job)

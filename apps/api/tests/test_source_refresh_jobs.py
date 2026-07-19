from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.domain import AppSetting, EbayListing, EbayRevisionJob, EbayRevisionJobStatus, ListingDraft, Product, SourceRefreshJobStatus, SupplierProduct
from app.services.ebay_revisions import enqueue_ebay_price_revisions, serialize_ebay_revision_job
from app.services.importer import recalculate_all_draft_prices
from app.services.source_refresh_jobs import (
    claim_next_source_refresh_job_any_batch,
    complete_source_refresh_job,
    create_automatic_source_refresh_batch,
    create_source_refresh_batch,
    fail_source_refresh_job,
    reject_suspicious_source_refresh_price,
    release_expired_source_refresh_jobs,
)


def make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def add_source_product(db, sku="SRC-AUTO-REFRESH", updated_at=None):
    product = Product(sku=sku, title="Auto Refresh Product")
    db.add(product)
    db.flush()
    supplier = SupplierProduct(
        product_id=product.id,
        supplier="home_depot",
        source_url=f"https://www.homedepot.com/p/Auto-Refresh/{sku}",
        supplier_sku=sku,
        last_price=20.0,
        last_shipping=0.0,
    )
    if updated_at is not None:
        supplier.updated_at = updated_at
    db.add(supplier)
    db.commit()
    return product


def add_ebay_listing(db, product, status="live"):
    listing = EbayListing(
        product_id=product.id,
        listing_id=f"ebay-{product.id}",
        account_id="main-store",
        environment="production",
        price=30.0,
        quantity=1,
        status=status,
    )
    db.add(listing)
    db.commit()
    return listing


def add_listing_draft(db, product, calculated_price=30.0):
    draft = ListingDraft(
        product_id=product.id,
        title=product.title,
        description="Test description",
        source_price=20.0,
        calculated_price=calculated_price,
        status="draft",
    )
    db.add(draft)
    db.commit()
    return draft


def test_automatic_source_refresh_queues_due_products_and_claims_next_job() -> None:
    db = make_session()
    product = add_source_product(db, updated_at=datetime.utcnow() - timedelta(hours=7))
    add_ebay_listing(db, product, status="scheduled")

    batch_key, due_available, jobs, message = create_automatic_source_refresh_batch(db)

    assert batch_key
    assert due_available == 1
    assert len(jobs) == 1
    assert jobs[0].status == SourceRefreshJobStatus.queued.value
    assert "Queued 1 supplier price refresh" in message

    claimed = claim_next_source_refresh_job_any_batch(db)

    assert claimed is not None
    assert claimed.id == jobs[0].id
    assert claimed.status == SourceRefreshJobStatus.running.value
    assert claimed.lease_expires_at is not None


def test_automatic_source_refresh_only_tracks_scheduled_and_live_listings() -> None:
    db = make_session()
    draft_only = add_source_product(db, sku="SRC-DRAFT-ONLY", updated_at=datetime.utcnow() - timedelta(hours=7))
    listed = add_source_product(db, sku="SRC-LIVE-ONLY", updated_at=datetime.utcnow() - timedelta(hours=7))
    add_ebay_listing(db, listed, status="live")

    batch_key, due_available, jobs, message = create_automatic_source_refresh_batch(db)

    assert batch_key
    assert due_available == 1
    assert len(jobs) == 1
    assert jobs[0].product_id == listed.id
    assert jobs[0].product_id != draft_only.id
    assert "Queued 1 supplier price refresh" in message


def test_automatic_source_refresh_respects_disabled_setting() -> None:
    db = make_session()
    add_source_product(db, updated_at=datetime.utcnow() - timedelta(hours=7))
    db.add(AppSetting(key="source_refresh_auto_enabled", value="False"))
    db.commit()

    batch_key, due_available, jobs, message = create_automatic_source_refresh_batch(db)

    assert batch_key is None
    assert due_available == 0
    assert jobs == []
    assert message == "Automatic source refresh is disabled."


def test_expired_source_refresh_job_returns_to_queue() -> None:
    db = make_session()
    add_source_product(db, updated_at=datetime.utcnow() - timedelta(hours=7))
    _batch_key, _due_available, jobs = create_source_refresh_batch(db, limit=1, interval_hours=6, force=False)
    job = claim_next_source_refresh_job_any_batch(db)
    assert job is not None
    job.lease_expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    released = release_expired_source_refresh_jobs(db)
    db.refresh(job)

    assert released == 1
    assert job.status == SourceRefreshJobStatus.queued.value
    assert jobs[0].id == job.id


def test_transient_browser_failure_retries_once_before_attention() -> None:
    db = make_session()
    add_source_product(db, updated_at=datetime.utcnow() - timedelta(hours=7))
    _batch_key, _due_available, jobs = create_source_refresh_batch(db, limit=1, interval_hours=6, force=False)
    job = claim_next_source_refresh_job_any_batch(db)

    retried = fail_source_refresh_job(db, job.id, "Failed to fetch")

    assert retried.status == SourceRefreshJobStatus.queued.value
    assert retried.completed_at is None
    assert retried.lease_expires_at is None
    assert "automatic retry in 1 minute" in retried.message

    retried.scheduled_for = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    second_attempt = claim_next_source_refresh_job_any_batch(db)
    second_retry = fail_source_refresh_job(db, second_attempt.id, "Failed to fetch")

    assert second_retry.status == SourceRefreshJobStatus.queued.value
    second_retry.scheduled_for = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    third_attempt = claim_next_source_refresh_job_any_batch(db)
    failed = fail_source_refresh_job(db, third_attempt.id, "Failed to fetch")

    assert failed.status == SourceRefreshJobStatus.failed.value
    assert failed.completed_at is not None


def test_completed_source_refresh_recalculates_before_queuing_revision() -> None:
    db = make_session()
    product = add_source_product(db, updated_at=datetime.utcnow() - timedelta(hours=7))
    supplier = product.supplier_products[0]
    draft = add_listing_draft(db, product, calculated_price=30.0)
    add_ebay_listing(db, product, status="live")
    _batch_key, _due_available, jobs = create_source_refresh_batch(db, limit=1, interval_hours=6, force=False)

    supplier.last_price = 10.0
    db.commit()
    completed = complete_source_refresh_job(db, jobs[0].id, product.id)
    db.refresh(draft)
    revision = db.scalar(select(EbayRevisionJob).where(EbayRevisionJob.product_id == product.id))

    assert completed is not None
    assert completed.captured_price == 10.0
    assert completed.price_changed is True
    assert completed.revision_queued is True
    assert draft.source_price == 10.0
    assert draft.calculated_price != 30.0
    assert revision is not None
    serialized_revision = serialize_ebay_revision_job(db, revision)
    assert serialized_revision["old_source_price"] == 20.0
    assert revision.source_price == 10.0
    assert revision.target_price == draft.calculated_price


def test_shipping_only_source_correction_cancels_stale_revision() -> None:
    db = make_session()
    product = add_source_product(db, updated_at=datetime.utcnow() - timedelta(hours=7))
    supplier = product.supplier_products[0]
    draft = add_listing_draft(db, product, calculated_price=30.0)
    listing = add_ebay_listing(db, product, status="scheduled")

    supplier.last_shipping = 0.0
    db.commit()
    recalculate_all_draft_prices(db, product_ids=[product.id])
    db.refresh(draft)
    listing.price = draft.calculated_price
    db.commit()

    supplier.last_shipping = 25.0
    db.commit()
    recalculate_all_draft_prices(db, product_ids=[product.id])
    queued, _updated = enqueue_ebay_price_revisions(db, product_ids=[product.id])
    revision = db.scalar(select(EbayRevisionJob).where(EbayRevisionJob.product_id == product.id))
    assert queued == 1
    assert revision is not None
    assert revision.status == EbayRevisionJobStatus.needs_review.value

    _batch_key, _due_available, jobs = create_source_refresh_batch(
        db, limit=1, interval_hours=6, force=True, product_ids={product.id}
    )
    supplier.last_shipping = 0.0
    db.commit()

    completed = complete_source_refresh_job(db, jobs[0].id, product.id)
    db.refresh(draft)
    db.refresh(revision)

    assert completed is not None
    assert completed.price_changed is False
    assert draft.calculated_price == listing.price
    assert revision.status == EbayRevisionJobStatus.cancelled.value
    assert revision.message == "Cancelled because the eBay price already matches the current draft price."


def test_source_refresh_rejects_five_dollar_promotion_false_positive() -> None:
    db = make_session()
    product = add_source_product(db, updated_at=datetime.utcnow() - timedelta(hours=7))
    _batch_key, _due_available, jobs = create_source_refresh_batch(db, limit=1, interval_hours=6, force=False)
    job = jobs[0]

    message = reject_suspicious_source_refresh_price(db, job.id, 5.0)

    db.refresh(job)
    db.refresh(product.supplier_products[0])
    assert message is not None
    assert "preserved the previous $20.00" in message
    assert job.status == SourceRefreshJobStatus.failed.value
    assert job.price_changed is False
    assert product.supplier_products[0].last_price == 20.0


def test_late_source_failure_does_not_overwrite_completed_capture() -> None:
    db = make_session()
    product = add_source_product(db, updated_at=datetime.utcnow() - timedelta(hours=7))
    _batch_key, _due_available, jobs = create_source_refresh_batch(db, limit=1, interval_hours=6, force=False)

    completed = complete_source_refresh_job(db, jobs[0].id, product.id)
    late_result = fail_source_refresh_job(db, jobs[0].id, "Home Depot showed an error page")

    assert completed is not None
    assert late_result is not None
    assert late_result.status == SourceRefreshJobStatus.completed.value
    assert late_result.message == completed.message


def test_older_queued_refresh_is_cancelled_after_newer_refresh_completed() -> None:
    db = make_session()
    product = add_source_product(db, updated_at=datetime.utcnow() - timedelta(hours=7))
    _first_batch, _due_available, first_jobs = create_source_refresh_batch(db, limit=1, interval_hours=6, force=False)
    old_job = first_jobs[0]
    old_job.status = SourceRefreshJobStatus.failed.value
    db.commit()

    _new_batch, _due_available, newer_jobs = create_source_refresh_batch(
        db, limit=1, interval_hours=6, force=True, product_ids={product.id}
    )
    newer_job = complete_source_refresh_job(db, newer_jobs[0].id, product.id)
    old_job.status = SourceRefreshJobStatus.queued.value
    old_job.scheduled_for = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    claimed = claim_next_source_refresh_job_any_batch(db)
    db.refresh(old_job)

    assert newer_job is not None
    assert claimed is None
    assert old_job.status == SourceRefreshJobStatus.cancelled.value
    assert f"#{newer_job.id}" in old_job.message

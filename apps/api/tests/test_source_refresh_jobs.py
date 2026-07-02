from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.domain import AppSetting, EbayListing, Product, SourceRefreshJobStatus, SupplierProduct
from app.services.source_refresh_jobs import (
    claim_next_source_refresh_job_any_batch,
    create_automatic_source_refresh_batch,
    create_source_refresh_batch,
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

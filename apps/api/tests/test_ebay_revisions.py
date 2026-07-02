from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.domain import EbayListing, EbayRevisionJob, EbayRevisionJobStatus
from app.services.ebay_revision_csv import build_ebay_price_revision_csv
from app.services.ebay_revisions import (
    MAX_REVISION_ATTEMPTS,
    release_expired_ebay_revision_jobs,
    start_next_ebay_revision_job,
    update_ebay_revision_job,
)


def make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def test_expired_revision_lease_returns_approved_job_to_queue() -> None:
    db = make_session()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=1,
        target_price=29.99,
        status=EbayRevisionJobStatus.running.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
        attempts=1,
        lease_expires_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(job)
    db.commit()

    assert release_expired_ebay_revision_jobs(db) == 1
    db.refresh(job)
    assert job.status == EbayRevisionJobStatus.queued.value
    assert job.started_at is None
    assert job.lease_expires_at is None
    assert "returned" in (job.message or "")


def test_revision_stops_after_repeated_timeouts() -> None:
    db = make_session()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=1,
        target_price=29.99,
        status=EbayRevisionJobStatus.running.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
        attempts=MAX_REVISION_ATTEMPTS,
        lease_expires_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(job)
    db.commit()

    assert release_expired_ebay_revision_jobs(db) == 1
    db.refresh(job)
    assert job.status == EbayRevisionJobStatus.failed.value
    assert job.completed_at is not None
    assert "manual attention" in (job.message or "")


def test_price_revision_sheet_preserves_info_and_only_writes_guarded_columns() -> None:
    db = make_session()
    listing = EbayListing(product_id=1, listing_id="800123456789", account_id="main-store", status="live", price=24.53)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="main-store",
        target_price=28.53,
        status=EbayRevisionJobStatus.queued.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()

    template = '#INFO,Version=0.0.2,Template=Edit price and quantity\nAction,Item number,Start price,Quantity\n'
    content, prepared_ids = build_ebay_price_revision_csv(
        db,
        account_key="main-store",
        job_ids=[job.id],
        template_csv=template,
    )

    assert prepared_ids == [job.id]
    assert content.startswith("#INFO,Version=0.0.2,Template=Edit price and quantity\r\n")
    assert "Action,Item number,Start price,Quantity\r\n" in content
    assert "Revise,800123456789,28.53,\r\n" in content


def test_price_revision_sheet_rejects_wrong_account() -> None:
    db = make_session()
    listing = EbayListing(product_id=1, listing_id="800123456789", account_id="main-store", status="live", price=24.53)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="main-store",
        target_price=28.53,
        status=EbayRevisionJobStatus.queued.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()

    try:
        build_ebay_price_revision_csv(
            db,
            account_key="second-store",
            job_ids=[job.id],
            template_csv="Action,Item number,Start price\n",
        )
    except ValueError as exc:
        assert "belongs to eBay account" in str(exc)
    else:
        raise AssertionError("Expected a cross-account sheet to be rejected")


def test_bulk_upload_mode_does_not_lease_browser_revision_jobs() -> None:
    db = make_session()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=1,
        target_price=29.99,
        status=EbayRevisionJobStatus.queued.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()

    assert start_next_ebay_revision_job(db) is None
    db.refresh(job)
    assert job.status == EbayRevisionJobStatus.queued.value
    assert job.attempts == 0


def test_pausing_revision_clears_browser_lease_without_completing_job() -> None:
    db = make_session()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=1,
        target_price=29.99,
        status=EbayRevisionJobStatus.running.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
        started_at=datetime.utcnow(),
        lease_expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.add(job)
    db.commit()

    update_ebay_revision_job(db, job, status=EbayRevisionJobStatus.paused.value)

    assert job.lease_expires_at is None
    assert job.completed_at is None

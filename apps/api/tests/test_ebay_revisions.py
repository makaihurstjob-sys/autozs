from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.domain import EbayListing, EbayRevisionBatchStatus, EbayRevisionJob, EbayRevisionJobStatus
from app.services.ebay_revision_batches import import_ebay_revision_result, prepare_next_ebay_revision_batch
from app.services.ebay_revision_csv import build_ebay_price_revision_csv, save_ebay_revision_template
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
    assert content.startswith("\ufeff#INFO,Version=0.0.2,Template=Edit price and quantity\r\n")
    assert "Action,Item number,Start price,Quantity\r\n" in content
    assert "Revise,800123456789,28.53,\r\n" in content


def test_real_ebay_template_drops_prefilled_listing_row() -> None:
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
    template = (
        "\ufeff#INFO,Version=1.0.0,Template= eBay-active-revise-price-quantity-download_US,,,,,,,,,\n"
        "Action,Category name,Item number,Title,Listing site,Currency,Start price,Buy It Now price,"
        "Available quantity,Relationship,Relationship details,Custom label (SKU)\n"
        'Revise,"Impact Drivers (168134)","800262913581",Old listing,"US","USD","123.53",,"1",,,\n'
    )

    content, _ = build_ebay_price_revision_csv(
        db,
        account_key="main-store",
        job_ids=[job.id],
        template_csv=template,
    )

    assert content.startswith("\ufeff#INFO,Version=1.0.0,Template= eBay-active-revise-price-quantity-download_US")
    assert "800262913581" not in content
    assert "Revise,,800123456789,,,USD" not in content
    assert "Revise,,800123456789,,," in content
    assert ",28.53," in content


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


def test_bulk_revision_batch_reconciles_success_and_failure_rows() -> None:
    db = make_session()
    save_ebay_revision_template(
        db,
        account_key="main-store",
        filename="edit-price.csv",
        template_csv="#INFO,Version=1.0.0\nAction,Item number,Start price,Quantity\n",
    )
    listings = [
        EbayListing(product_id=1, listing_id="800123456781", account_id="main-store", status="live", price=20.0),
        EbayListing(product_id=2, listing_id="800123456782", account_id="main-store", status="scheduled", price=30.0),
    ]
    db.add_all(listings)
    db.flush()
    jobs = [
        EbayRevisionJob(
            product_id=index,
            ebay_listing_id=listing.id,
            ebay_account_key="main-store",
            old_price=listing.price,
            target_price=listing.price + 5,
            status=EbayRevisionJobStatus.queued.value,
            guard_passed=True,
            approval_required=False,
            approved_at=datetime.utcnow(),
        )
        for index, listing in enumerate(listings, start=1)
    ]
    db.add_all(jobs)
    db.commit()

    batch = prepare_next_ebay_revision_batch(db, account_key="main-store")
    assert batch is not None
    assert batch.status == EbayRevisionBatchStatus.prepared.value
    assert batch.rows_total == 2
    assert all(job.status == EbayRevisionJobStatus.running.value for job in jobs)
    assert "Revise,800123456781,25.00" in batch.csv_content

    result = (
        "#INFO,Version=1.0.0\n"
        "Action,Item number,Status,Error message\n"
        "Revise,800123456781,Success,\n"
        'Revise,800123456782,Failed,"Listing is not eligible for revision"\n'
    )
    imported = import_ebay_revision_result(db, batch, result_csv=result, filename="results.csv")
    assert imported.status == EbayRevisionBatchStatus.needs_review.value
    assert imported.rows_succeeded == 1
    assert imported.rows_failed == 1
    db.refresh(jobs[0])
    db.refresh(jobs[1])
    db.refresh(listings[0])
    assert jobs[0].status == EbayRevisionJobStatus.completed.value
    assert listings[0].price == 25.0
    assert jobs[1].status == EbayRevisionJobStatus.paused.value
    assert "not eligible" in (jobs[1].message or "")


def test_bulk_revision_result_pauses_job_missing_from_results() -> None:
    db = make_session()
    save_ebay_revision_template(
        db,
        account_key="main-store",
        filename="edit-price.csv",
        template_csv="Action,Item number,Start price\n",
    )
    listing = EbayListing(product_id=1, listing_id="800123456789", account_id="main-store", status="live", price=20.0)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="main-store",
        target_price=25.0,
        status=EbayRevisionJobStatus.queued.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    batch = prepare_next_ebay_revision_batch(db, account_key="main-store")
    assert batch is not None

    import_ebay_revision_result(
        db,
        batch,
        result_csv="Item number,Status,Error message\n800999999999,Success,\n",
    )
    db.refresh(job)
    assert job.status == EbayRevisionJobStatus.paused.value
    assert "did not contain this item" in (job.message or "")

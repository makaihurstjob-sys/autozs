from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.domain import (
    EbayListing,
    EbayRevisionBatch,
    EbayRevisionBatchStatus,
    EbayRevisionJob,
    EbayRevisionJobStatus,
    ListingDraft,
    Product,
    SupplierProduct,
)
from app.services.ebay_revision_batches import (
    decode_ebay_revision_result,
    import_ebay_revision_result,
    list_ebay_revision_batches,
    prepare_next_ebay_revision_batch,
)
from app.services.ebay_revision_csv import build_ebay_price_revision_csv, save_ebay_revision_template
from app.services.ebay_sync import _sync_local_draft_status
from app.services.ebay_revisions import (
    MAX_REVISION_ATTEMPTS,
    OUT_OF_STOCK_ACTION,
    RESTOCK_ACTION,
    cancel_revision_jobs_for_ebay_listing,
    enqueue_ebay_price_revisions,
    enqueue_ebay_stock_revisions,
    list_ebay_revision_jobs,
    release_expired_ebay_revision_jobs,
    start_next_ebay_revision_job,
    supplier_availability_block,
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


def test_tombstoned_listing_cancels_open_revision_jobs_on_read() -> None:
    db = make_session()
    listing = EbayListing(product_id=1, listing_id="800123456789", account_id="a.m.anim-59", status="tombstoned", price=30.53)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="a.m.anim-59",
        old_price=30.53,
        target_price=31.53,
        status=EbayRevisionJobStatus.needs_review.value,
    )
    db.add(job)
    db.commit()

    jobs = list_ebay_revision_jobs(db)

    assert len(jobs) == 1
    assert jobs[0].status == EbayRevisionJobStatus.cancelled.value
    assert jobs[0].completed_at is not None
    assert "tombstoned" in (jobs[0].message or "")


def test_tombstone_helper_cancels_linked_revision_jobs() -> None:
    db = make_session()
    listing = EbayListing(product_id=1, listing_id="800123456789", account_id="a.m.anim-59", status="scheduled", price=30.53)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="a.m.anim-59",
        old_price=30.53,
        target_price=31.53,
        status=EbayRevisionJobStatus.queued.value,
        lease_expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    db.add(job)
    db.commit()

    cancelled = cancel_revision_jobs_for_ebay_listing(db, listing, reason="test tombstone")

    assert cancelled == 1
    db.refresh(job)
    assert job.status == EbayRevisionJobStatus.cancelled.value
    assert job.lease_expires_at is None
    assert job.message == "test tombstone"


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
    listing = EbayListing(product_id=1, listing_id="800123456789", account_id="a.m.anim-59", status="live", price=24.53)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="a.m.anim-59",
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
        account_key="a.m.anim-59",
        job_ids=[job.id],
        template_csv=template,
    )

    assert prepared_ids == [job.id]
    assert content.startswith("\ufeff#INFO,Version=0.0.2,Template=Edit price and quantity\r\n")
    assert "Action,Item number,Start price,Quantity\r\n" in content
    assert "Revise,800123456789,28.53,\r\n" in content


def test_pack_revision_sheet_includes_required_pack_title() -> None:
    db = make_session()
    product = Product(sku="SRC-PACK", title="Minimum order product")
    db.add(product)
    db.flush()
    db.add_all(
        [
            SupplierProduct(
                product_id=product.id,
                source_url="https://www.homedepot.com/p/example/123",
                last_price=14.19,
                minimum_order_quantity=2,
            ),
            ListingDraft(product_id=product.id, title="(2X) Minimum order product | FREE SHIPPING", description="Pack"),
        ]
    )
    listing = EbayListing(product_id=product.id, listing_id="800123456789", account_id="a.m.anim-59", status="scheduled", price=20.53)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=product.id,
        ebay_listing_id=listing.id,
        ebay_account_key="a.m.anim-59",
        target_price=36.53,
        status=EbayRevisionJobStatus.queued.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()

    content, prepared_ids = build_ebay_price_revision_csv(
        db,
        account_key="a.m.anim-59",
        job_ids=[job.id],
        template_csv="Action,Item number,Start price,Quantity\n",
    )

    assert prepared_ids == [job.id]
    assert "Action,Item number,Start price,Quantity,Title\r\n" in content
    assert "Revise,800123456789,36.53,,(2X) Minimum order product | FREE SHIPPING\r\n" in content


def test_real_ebay_template_drops_prefilled_listing_row() -> None:
    db = make_session()
    listing = EbayListing(product_id=1, listing_id="800123456789", account_id="a.m.anim-59", status="live", price=24.53)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="a.m.anim-59",
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
        account_key="a.m.anim-59",
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
    listing = EbayListing(product_id=1, listing_id="800123456789", account_id="a.m.anim-59", status="live", price=24.53)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="a.m.anim-59",
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
        account_key="a.m.anim-59",
        filename="edit-price.csv",
        template_csv="#INFO,Version=1.0.0\nAction,Item number,Start price,Quantity\n",
    )
    listings = [
        EbayListing(product_id=1, listing_id="800123456781", account_id="a.m.anim-59", status="live", price=20.0),
        EbayListing(product_id=2, listing_id="800123456782", account_id="a.m.anim-59", status="scheduled", price=30.0),
    ]
    db.add_all(listings)
    db.flush()
    jobs = [
        EbayRevisionJob(
            product_id=index,
            ebay_listing_id=listing.id,
            ebay_account_key="a.m.anim-59",
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

    batch = prepare_next_ebay_revision_batch(db, account_key="a.m.anim-59")
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
    assert imported.result_filename == "results.csv"
    assert imported.rows_succeeded == 1
    assert imported.rows_failed == 1
    db.refresh(jobs[0])
    db.refresh(jobs[1])
    db.refresh(listings[0])
    assert jobs[0].status == EbayRevisionJobStatus.completed.value
    assert listings[0].price == 25.0
    assert jobs[1].status == EbayRevisionJobStatus.paused.value
    assert "not eligible" in (jobs[1].message or "")


def test_revision_result_can_be_decoded_from_extension_base64() -> None:
    import base64

    result = "Action,Item number,Status\nRevise,800123456789,Success\n"
    encoded = base64.b64encode(result.encode("utf-8")).decode("ascii")

    assert decode_ebay_revision_result(filename="result.csv", result_base64=encoded) == result


def test_bulk_revision_result_accepts_ebay_itemid_warning_row() -> None:
    db = make_session()
    listing = EbayListing(product_id=1, listing_id="800123456789", account_id="a.m.anim-59", status="scheduled", price=20.0)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="a.m.anim-59",
        target_price=22.0,
        status=EbayRevisionJobStatus.running.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    batch = EbayRevisionBatch(
        account_key="a.m.anim-59",
        status=EbayRevisionBatchStatus.waiting_results.value,
        job_ids_json=f"[{job.id}]",
        filename="revision.csv",
        csv_content="Action,Item number,Start price\nRevise,800123456789,22.00\n",
        rows_total=1,
    )
    db.add(batch)
    db.commit()

    result = (
        "Line Number,Action,Status,ErrorCode,ErrorMessage,WarningCode,WarningMessage,ItemID\n"
        "2,Revise,Warning,,,21917236,Funds may be held,800123456789\n"
    )
    imported = import_ebay_revision_result(db, batch, result_csv=result, filename="results.csv")

    assert imported.status == EbayRevisionBatchStatus.completed.value
    db.refresh(job)
    db.refresh(listing)
    assert job.status == EbayRevisionJobStatus.completed.value
    assert listing.price == 22.0


def test_bulk_revision_result_pauses_job_missing_from_results() -> None:
    db = make_session()
    save_ebay_revision_template(
        db,
        account_key="a.m.anim-59",
        filename="edit-price.csv",
        template_csv="Action,Item number,Start price\n",
    )
    listing = EbayListing(product_id=1, listing_id="800123456789", account_id="a.m.anim-59", status="live", price=20.0)
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="a.m.anim-59",
        target_price=25.0,
        status=EbayRevisionJobStatus.queued.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    batch = prepare_next_ebay_revision_batch(db, account_key="a.m.anim-59")
    assert batch is not None

    import_ebay_revision_result(
        db,
        batch,
        result_csv="Item number,Status,Error message\n800999999999,Success,\n",
    )
    db.refresh(job)
    assert job.status == EbayRevisionJobStatus.paused.value
    assert "did not contain this item" in (job.message or "")


def test_revision_batches_list_is_newest_first_and_filterable() -> None:
    db = make_session()
    batches = [
        EbayRevisionBatch(
            account_key="secondary-store",
            status=EbayRevisionBatchStatus.completed.value,
            job_ids_json="[3]",
            filename="secondary.csv",
            csv_content="Action,Item number,Start price\n",
            rows_total=1,
        ),
        EbayRevisionBatch(
            account_key="a.m.anim-59",
            status=EbayRevisionBatchStatus.prepared.value,
            job_ids_json="[2]",
            filename="newest.csv",
            csv_content="Action,Item number,Start price\n",
            rows_total=1,
        ),
    ]
    db.add_all(batches)
    db.commit()

    assert [batch.filename for batch in list_ebay_revision_batches(db)] == ["newest.csv", "secondary.csv"]
    assert [batch.filename for batch in list_ebay_revision_batches(db, account_key="a.m.anim-59")] == ["newest.csv"]
    assert [batch.filename for batch in list_ebay_revision_batches(db, status="completed")] == ["secondary.csv"]


def _priced_product(db, *, cost: float, draft_price: float, live_price: float, shipping: float = 0.0):
    product = Product(sku=f"SKU-{cost}-{draft_price}", title="Test planter", status="monitoring")
    db.add(product)
    db.flush()
    db.add(SupplierProduct(product_id=product.id, supplier="home_depot", source_url="https://example.com/p/1",
                           last_price=cost, last_shipping=shipping))
    db.add(ListingDraft(product_id=product.id, marketplace="ebay", title="Test planter", description="d", calculated_price=draft_price))
    listing = EbayListing(
        product_id=product.id,
        listing_id=f"8004{int(live_price * 100)}",
        account_id="a.m.anim-59",
        status="active",
        price=live_price,
        quantity=1,
    )
    db.add(listing)
    db.commit()
    return product, listing


def test_below_cost_revision_target_is_never_proposed() -> None:
    """A draft price under supplier cost is a data fault, not a pricing decision.

    Regression: this proposal regenerated on every repricing pass and, once
    approved, would have sold the item at a loss.
    """
    db = make_session()
    _priced_product(db, cost=44.97, draft_price=12.53, live_price=56.53)

    queued, updated = enqueue_ebay_price_revisions(db)

    assert (queued, updated) == (0, 0)
    assert db.query(EbayRevisionJob).count() == 0


def test_profitable_revision_target_is_still_proposed() -> None:
    db = make_session()
    _priced_product(db, cost=44.97, draft_price=59.53, live_price=56.53)

    queued, _ = enqueue_ebay_price_revisions(db)

    assert queued == 1
    job = db.query(EbayRevisionJob).one()
    assert job.target_price == 59.53
    assert job.projected_profit > 0


def _enable_revision_auto_approval(db) -> None:
    from app.models.domain import AppSetting

    db.add_all([
        AppSetting(key="ebay_revision_auto_approve_enabled", value="true"),
        AppSetting(key="ebay_revision_max_change_percent", value="25"),
        AppSetting(key="source_refresh_interval_hours", value="6"),
        AppSetting(key="default_min_profit_guard_enabled", value="true"),
        AppSetting(key="default_min_profit", value="2"),
    ])
    db.commit()


def test_fresh_guarded_price_revision_is_automatically_approved() -> None:
    db = make_session()
    _enable_revision_auto_approval(db)
    _priced_product(db, cost=20.0, draft_price=39.53, live_price=38.53)

    enqueue_ebay_price_revisions(db)

    job = db.query(EbayRevisionJob).one()
    assert job.guard_passed is True
    assert job.status == EbayRevisionJobStatus.queued.value
    assert job.approval_required is False
    assert job.approved_at is not None


def test_stale_supplier_evidence_keeps_price_revision_in_manual_review() -> None:
    db = make_session()
    _enable_revision_auto_approval(db)
    _priced_product(db, cost=20.0, draft_price=39.53, live_price=38.53)
    supplier = db.query(SupplierProduct).one()
    supplier.updated_at = datetime.utcnow() - timedelta(hours=7)
    db.commit()

    enqueue_ebay_price_revisions(db)

    job = db.query(EbayRevisionJob).one()
    assert job.guard_passed is True
    assert job.status == EbayRevisionJobStatus.needs_review.value
    assert job.approval_required is True
    assert job.approved_at is None
    assert "older than 6 hours" in (job.guard_reason or "")


def test_zero_quantity_listing_is_never_auto_approved_for_price_change() -> None:
    db = make_session()
    _enable_revision_auto_approval(db)
    _, listing = _priced_product(db, cost=20.0, draft_price=39.53, live_price=38.53)
    listing.quantity = 0
    db.commit()

    enqueue_ebay_price_revisions(db)

    job = db.query(EbayRevisionJob).one()
    assert job.status == EbayRevisionJobStatus.needs_review.value
    assert job.approval_required is True


def test_oversized_price_change_is_never_auto_approved() -> None:
    db = make_session()
    _enable_revision_auto_approval(db)
    _priced_product(db, cost=20.0, draft_price=55.53, live_price=38.53)

    enqueue_ebay_price_revisions(db)

    job = db.query(EbayRevisionJob).one()
    assert job.guard_passed is True
    assert job.status == EbayRevisionJobStatus.needs_review.value
    assert "exceeds" in (job.guard_reason or "")


def test_below_cost_target_cancels_an_existing_open_revision() -> None:
    db = make_session()
    product, listing = _priced_product(db, cost=44.97, draft_price=12.53, live_price=56.53)
    stale = EbayRevisionJob(
        product_id=product.id,
        ebay_listing_id=listing.id,
        target_price=12.53,
        status=EbayRevisionJobStatus.needs_review.value,
        guard_passed=False,
    )
    db.add(stale)
    db.commit()

    enqueue_ebay_price_revisions(db)

    db.refresh(stale)
    assert stale.status == EbayRevisionJobStatus.cancelled.value
    assert "below cost" in (stale.message or "")


def test_ebay_sync_does_not_overwrite_the_engine_draft_price() -> None:
    """The live eBay price must not become the pricing engine's target.

    Regression: syncing the observed price into calculated_price closed a loop in
    which a mispriced live listing overwrote the engine's intended price, so the
    revision generator proposed the wrong price straight back to eBay and the
    mispricing could never self-correct.
    """
    db = make_session()
    product = Product(sku="SYNC-1", title="Test planter", status="monitoring")
    db.add(product)
    db.flush()
    draft = ListingDraft(product_id=product.id, marketplace="ebay", title="Test planter", description="d", calculated_price=56.53)
    db.add(draft)
    db.commit()

    _sync_local_draft_status(db, product.id, {"status": "active", "price": 12.53, "draft_id": None})
    db.commit()

    db.refresh(draft)
    assert draft.calculated_price == 56.53, "sync overwrote the engine price with the live eBay price"
    assert draft.status == "active", "sync should still track listing status"


def test_breakeven_revisions_survive_the_guard_and_the_below_cost_skip() -> None:
    """Breakeven targets zero profit, which must not read as 'selling below cost'.

    Two things would otherwise silently kill the mode: the minimum-profit guard
    (profit 0.00 < the 2.00 floor) and the below-cost skip, which cent-rounding can
    trip when the computed profit lands at -0.01.
    """
    from app.models.domain import AppSetting
    from app.services.importer import calculate_listing_price, effective_landed_cost
    from app.services.settings import read_pricing_settings

    db = make_session()
    db.add(AppSetting(key="default_pricing_strategy", value="breakeven"))
    db.add(AppSetting(key="default_min_profit_guard_enabled", value="true"))
    db.add(AppSetting(key="default_min_profit", value="2.0"))
    db.commit()

    settings = read_pricing_settings(db)
    landed = effective_landed_cost(44.97, 0.0, settings)
    breakeven_price = calculate_listing_price(landed, None, settings).final_price

    _priced_product(db, cost=44.97, draft_price=breakeven_price, live_price=99.53)

    queued, _ = enqueue_ebay_price_revisions(db)

    assert queued == 1, "breakeven proposal was suppressed as below cost"
    job = db.query(EbayRevisionJob).one()
    assert job.target_price == breakeven_price
    assert job.minimum_profit == 0.0, "breakeven must not be held to the normal profit floor"
    assert job.guard_passed is True, f"guard blocked breakeven: {job.guard_reason}"


def _sourced_product(
    db,
    *,
    shipping: float,
    in_stock: bool = True,
    price_unavailable: bool = False,
    cost: float = 9.47,
    draft_price: float = 14.53,
    live_price: float = 14.53,
):
    product = Product(
        sku=f"SKU-STOCK-{shipping}-{in_stock}-{price_unavailable}",
        title="Plant food",
        status="monitoring",
    )
    db.add(product)
    db.flush()
    db.add(
        SupplierProduct(
            product_id=product.id,
            supplier="home_depot",
            source_url="https://www.homedepot.com/p/example/100013303",
            last_price=None if price_unavailable else cost,
            last_shipping=shipping,
            in_stock=in_stock,
            price_unavailable=price_unavailable,
        )
    )
    db.add(
        ListingDraft(
            product_id=product.id,
            marketplace="ebay",
            title="Plant food",
            description="d",
            calculated_price=draft_price,
        )
    )
    listing = EbayListing(
        product_id=product.id,
        listing_id="800456297709",
        account_id="a.m.anim-59",
        status="active",
        price=live_price,
        quantity=1,
    )
    db.add(listing)
    db.commit()
    return product, listing


def test_supplier_without_shipping_is_treated_as_unfulfillable() -> None:
    """Home Depot stops rendering a delivery option once an item is unavailable, and the
    capture stores that as shipping = -1.0. No shipping offered means we cannot fulfil it."""
    db = make_session()
    _sourced_product(db, shipping=-1.0)
    supplier = db.query(SupplierProduct).one()

    assert supplier_availability_block(supplier) == "the supplier is not offering a shipping option"


def test_unfulfillable_listing_is_marked_out_of_stock_without_approval() -> None:
    db = make_session()
    _sourced_product(db, shipping=-1.0)

    blocked, released = enqueue_ebay_stock_revisions(db)

    assert (blocked, released) == (1, 0)
    job = db.query(EbayRevisionJob).one()
    assert job.action == OUT_OF_STOCK_ACTION
    # Zeroing quantity cannot lose money, so it must not wait behind a human.
    assert job.status == EbayRevisionJobStatus.queued.value
    assert job.approval_required is False
    assert job.approved_at is not None
    assert "out of stock" in (job.message or "")


def test_out_of_stock_covers_missing_price_and_explicit_out_of_stock() -> None:
    for kwargs in ({"shipping": 0.0, "in_stock": False}, {"shipping": 0.0, "price_unavailable": True}):
        db = make_session()
        _sourced_product(db, **kwargs)

        blocked, _ = enqueue_ebay_stock_revisions(db)

        assert blocked == 1, f"expected an out-of-stock revision for {kwargs}"
        assert db.query(EbayRevisionJob).one().action == OUT_OF_STOCK_ACTION


def test_unfulfillable_product_is_not_repriced_and_cancels_a_stuck_proposal() -> None:
    """Regression: proposals for products with unknown shipping failed their guard and sat
    in review forever, because a price change was being proposed for something that could
    not be bought at all."""
    db = make_session()
    product, listing = _sourced_product(db, shipping=-1.0, draft_price=17.53, live_price=21.53)
    stuck = EbayRevisionJob(
        product_id=product.id,
        ebay_listing_id=listing.id,
        ebay_account_key="a.m.anim-59",
        target_price=17.53,
        status=EbayRevisionJobStatus.needs_review.value,
        guard_passed=False,
        guard_reason="Supplier shipping is unknown",
    )
    db.add(stuck)
    db.commit()

    queued, updated = enqueue_ebay_price_revisions(db)

    assert (queued, updated) == (0, 0), "an unfulfillable product must not be repriced"
    db.refresh(stuck)
    assert stuck.status == EbayRevisionJobStatus.cancelled.value
    assert "out of stock" in (stuck.message or "")
    stock_jobs = db.query(EbayRevisionJob).filter(EbayRevisionJob.action == OUT_OF_STOCK_ACTION).all()
    assert len(stock_jobs) == 1


def test_restock_only_releases_listings_autozs_actually_took_down() -> None:
    """EbayListing.quantity defaults to 0 and is not reliably synced, so restock keys off an
    applied out-of-stock revision instead of the stored quantity."""
    db = make_session()
    _, listing = _sourced_product(db, shipping=0.0)

    # A healthy listing that was never zeroed must be left alone.
    assert enqueue_ebay_stock_revisions(db) == (0, 0)
    assert db.query(EbayRevisionJob).count() == 0

    db.add(
        EbayRevisionJob(
            product_id=listing.product_id,
            ebay_listing_id=listing.id,
            ebay_account_key="a.m.anim-59",
            action=OUT_OF_STOCK_ACTION,
            target_price=14.53,
            status=EbayRevisionJobStatus.completed.value,
            completed_at=datetime.utcnow(),
            guard_passed=True,
            approval_required=False,
        )
    )
    db.commit()

    blocked, released = enqueue_ebay_stock_revisions(db)

    assert (blocked, released) == (0, 1)
    restock = db.query(EbayRevisionJob).filter(EbayRevisionJob.action == RESTOCK_ACTION).one()
    assert restock.status == EbayRevisionJobStatus.queued.value


def test_already_out_of_stock_listing_is_not_zeroed_twice() -> None:
    db = make_session()
    _, listing = _sourced_product(db, shipping=-1.0)
    db.add(
        EbayRevisionJob(
            product_id=listing.product_id,
            ebay_listing_id=listing.id,
            ebay_account_key="a.m.anim-59",
            action=OUT_OF_STOCK_ACTION,
            target_price=14.53,
            status=EbayRevisionJobStatus.completed.value,
            completed_at=datetime.utcnow(),
            guard_passed=True,
            approval_required=False,
        )
    )
    db.commit()

    assert enqueue_ebay_stock_revisions(db) == (0, 0)
    assert db.query(EbayRevisionJob).count() == 1


def _stock_sheet_job(db):
    listing = EbayListing(
        product_id=1, listing_id="800123456789", account_id="a.m.anim-59", status="live", price=24.53
    )
    db.add(listing)
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=listing.id,
        ebay_account_key="a.m.anim-59",
        action=OUT_OF_STOCK_ACTION,
        target_price=24.53,
        status=EbayRevisionJobStatus.queued.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    return job


def test_out_of_stock_sheet_writes_quantity_zero_and_leaves_price_untouched() -> None:
    db = make_session()
    job = _stock_sheet_job(db)

    template = "#INFO,Version=0.0.2,Template=Edit price and quantity\nAction,Item number,Start price,Quantity\n"
    content, prepared_ids = build_ebay_price_revision_csv(
        db,
        account_key="a.m.anim-59",
        job_ids=[job.id],
        template_csv=template,
    )

    assert prepared_ids == [job.id]
    # Start price stays blank on purpose: eBay changes only the fields a row populates, so
    # re-asserting a price could push a stale value at a listing we only meant to take down.
    assert "Revise,800123456789,,0\r\n" in content


def test_out_of_stock_sheet_adds_a_quantity_column_when_the_template_lacks_one() -> None:
    db = make_session()
    job = _stock_sheet_job(db)

    content, _ = build_ebay_price_revision_csv(
        db,
        account_key="a.m.anim-59",
        job_ids=[job.id],
        template_csv="Action,Item number,Start price\n",
    )

    # Appended with eBay's own column name so the sheet stays importable.
    assert "Action,Item number,Start price,Available quantity\r\n" in content
    assert "Revise,800123456789,,0\r\n" in content


def test_duplicate_retirement_tombstones_sibling_rows_for_same_ebay_item() -> None:
    db = make_session()
    live = EbayListing(
        product_id=1, listing_id="800123456789", account_id="a.m.anim-59", environment="manual", status="active", price=24.53, quantity=1
    )
    scheduled = EbayListing(
        product_id=1, listing_id="800123456789", account_id="legacy-import", environment="production", status="scheduled", price=24.53, quantity=1
    )
    db.add_all([live, scheduled])
    db.flush()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=live.id,
        ebay_account_key="a.m.anim-59",
        action="retire_duplicate",
        target_price=24.53,
        status=EbayRevisionJobStatus.running.value,
        guard_passed=True,
        guard_reason="Preserve the canonical listing.",
        approval_required=False,
    )
    db.add(job)
    db.commit()

    update_ebay_revision_job(db, job, status=EbayRevisionJobStatus.completed.value)

    db.refresh(live)
    db.refresh(scheduled)
    assert live.quantity == 0
    assert live.relist_blocked is True
    assert scheduled.quantity == 0
    assert scheduled.status == "tombstoned"
    assert scheduled.relist_blocked is True
    assert scheduled.removal_reason == "duplicate_supplier_listing"



# Transcribed from the account's saved eBay download
# (eBay-active-revise-price-quantity-download_US). The quantity column is named
# "Available quantity"; matching only "Quantity" appended a second, dead column and left
# the real one blank, so the listing would never actually have gone out of stock.
REAL_EBAY_TEMPLATE = (
    "#INFO,Version=1.0.0,Template= eBay-active-revise-price-quantity-download_US,,,,,,,,,\n"
    "Action,Category name,Item number,Title,Listing site,Currency,Start price,"
    "Buy It Now price,Available quantity,Relationship,Relationship details,Custom label (SKU)\n"
)


def test_out_of_stock_uses_the_real_ebay_available_quantity_column() -> None:
    db = make_session()
    job = _stock_sheet_job(db)

    content, prepared_ids = build_ebay_price_revision_csv(
        db,
        account_key="a.m.anim-59",
        job_ids=[job.id],
        template_csv=REAL_EBAY_TEMPLATE,
    )

    assert prepared_ids == [job.id]
    header = next(line for line in content.splitlines() if line.startswith("Action,"))
    assert header.count("Available quantity") == 1, f"column was duplicated: {header}"
    assert "Quantity," not in header.replace("Available quantity", ""), header

    row = next(line for line in content.splitlines() if line.startswith("Revise,"))
    cells = row.split(",")
    assert cells[2] == "800123456789", cells
    assert cells[6] == "", f"start price must stay blank on a stock revision: {cells}"
    assert cells[8] == "0", f"available quantity must be 0: {cells}"


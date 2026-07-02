from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.domain import EbayListing, EbayRevisionJob, EbaySyncRun, ListingDraft, ListingJob, Product
from app.services.ebay_report_files import import_ebay_report_file, parse_ebay_listing_report, scan_ebay_report_inbox
from app.services.ebay_revision_batches import prepare_next_ebay_revision_batch
from app.services.ebay_revision_csv import save_ebay_revision_template


def test_automatic_active_listings_report_imports_real_ebay_csv_and_preserves_scheduled(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'report-test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    report_path = tmp_path / "ebay-active-listings-main-store-run-1.csv"
    report_path.write_text(
        "\ufeffItem number,Title,Variation details,Custom label (SKU),Available quantity,Format,Currency,Start price,"
        "Auction Buy It Now price,Reserve price,Current price,Sold quantity,Watchers,Bids,Start date,End date\n"
        '"800262913581","Impact Driver",,"SYNC-TARGET","1","FIXED_PRICE","USD",123.53,,,123.53,"0","","",'
        '"Jun-29-26 16:00:01 PDT","Jul-29-26 16:00:01 PDT"\n',
        encoding="utf-8",
    )

    with Session() as db:
        products = [Product(sku=sku, title=sku) for sku in ("SYNC-TARGET", "ACTIVE-MISSING", "SCHEDULED-MISSING", "STALE-SCHEDULED")]
        db.add_all(products)
        db.flush()
        for product in products:
            db.add(ListingDraft(product_id=product.id, marketplace="ebay", title=product.title, description="test", status="draft"))
        db.add_all(
            [
                EbayListing(product_id=products[0].id, listing_id="800262913581", account_id="main-store", status="scheduled", views=7),
                EbayListing(product_id=products[1].id, listing_id="ACTIVE-MISSING-1", account_id="main-store", status="active"),
                EbayListing(product_id=products[2].id, listing_id="SCHEDULED-MISSING-1", account_id="main-store", status="scheduled"),
                EbayListing(product_id=products[3].id, listing_id="STALE-SCHEDULED-1", account_id="main-store", status="scheduled"),
                ListingJob(
                    product_id=products[3].id,
                    ebay_account_key="main-store",
                    action="create_draft",
                    status="needs_review",
                    ebay_draft_id="5127501611603",
                    listing_schedule_at=datetime.utcnow() - timedelta(days=1),
                ),
            ]
        )
        run = EbaySyncRun(id=1, account_key="main-store", status="running", phase="report_downloaded")
        db.add(run)
        db.commit()

        rows = parse_ebay_listing_report(report_path)
        assert rows[0]["Custom label (SKU)"] == "SYNC-TARGET"
        imported = import_ebay_report_file(db, report_path, run_id=1, account_key="main-store")
        assert imported.status == "completed"
        assert imported.listings_seen == 1

        listings = {item.listing_id: item for item in db.scalars(select(EbayListing)).all()}
        assert listings["800262913581"].status == "active"
        assert listings["800262913581"].price == 123.53
        assert listings["800262913581"].views == 7
        assert listings["800262913581"].started_at.isoformat() == "2026-06-29T16:00:01"
        assert listings["800262913581"].renews_at.isoformat() == "2026-07-29T16:00:01"
        assert listings["ACTIVE-MISSING-1"].status == "tombstoned"
        assert listings["SCHEDULED-MISSING-1"].status == "scheduled"
        assert listings["STALE-SCHEDULED-1"].status == "tombstoned"
        stale_job = db.scalar(select(ListingJob).where(ListingJob.product_id == products[3].id))
        assert stale_job.status == "tombstoned"


def test_revision_result_download_is_imported_and_archived(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'revision-result-test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        product = Product(sku="REVISION-TARGET", title="Revision target")
        db.add(product)
        db.flush()
        listing = EbayListing(
            product_id=product.id,
            listing_id="800123456789",
            account_id="main-store",
            status="scheduled",
            price=20.0,
        )
        db.add(listing)
        db.flush()
        job = EbayRevisionJob(
            product_id=product.id,
            ebay_listing_id=listing.id,
            ebay_account_key="main-store",
            old_price=20.0,
            target_price=25.0,
            status="queued",
            guard_passed=True,
            approval_required=False,
            approved_at=datetime.utcnow(),
        )
        db.add(job)
        save_ebay_revision_template(
            db,
            account_key="main-store",
            filename="edit-price.csv",
            template_csv="Action,Item number,Start price\n",
        )
        batch = prepare_next_ebay_revision_batch(db, account_key="main-store")
        assert batch is not None
        result_path = tmp_path / f"ebay-revision-results-main-store-batch-{batch.id}.csv"
        result_path.write_text("Action,Item number,Status,Error message\nRevise,800123456789,Success,\n")

        imported = scan_ebay_report_inbox(db, inbox=tmp_path)

        assert imported == [batch.id]
        db.refresh(job)
        db.refresh(listing)
        assert job.status == "completed"
        assert listing.price == 25.0
        assert not result_path.exists()
        assert (tmp_path / "processed" / result_path.name).exists()

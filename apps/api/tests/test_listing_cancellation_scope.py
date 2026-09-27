from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.domain import Product, SupplierProduct, EbayListing, ListingJob, AppSetting
from app.schemas.domain import ListingJobUpdate
from app.services.listing_exclusions import listing_exclusion_reason
from app.services.ebay_revisions import stock_restoration_block
from app.services.listing_jobs import update_listing_job, serialize_listing_job_lite


@pytest.fixture
def records():
    engine = create_engine("sqlite:///:memory:")
    for model in (Product, SupplierProduct, EbayListing, ListingJob, AppSetting):
        model.__table__.create(engine)
    with Session(engine) as db:
        product = Product(sku="scope", title="Scope", status="monitoring")
        db.add(product)
        db.flush()
        now = datetime.utcnow()
        supplier = SupplierProduct(product_id=product.id, supplier="home_depot", source_url="https://example.test/item", in_stock=True, last_price=10, last_shipping=0, stock_observed_at=now, price_observed_at=now, shipping_observed_at=now)
        listing = EbayListing(product_id=product.id, listing_id="123", status="active", quantity=0, price=20)
        job = ListingJob(product_id=product.id, action="publish", status="cancelled", message="Cancel duplicate and restore existing listing")
        db.add_all([supplier, listing, job])
        db.commit()
        yield db, product, supplier, listing, job
    engine.dispose()


def test_legacy_cancel_message_cannot_authorize_restoration(records):
    db, _, _, listing, job = records
    assert job.cancellation_scope == "product"
    assert stock_restoration_block(db, listing)


def test_explicit_scope_preserves_publication_exclusion(records):
    db, product, _, listing, job = records
    update_listing_job(db, job, status="cancelled", cancellation_scope="publication_only")
    db.expire_all()
    assert stock_restoration_block(db, listing) is None
    assert listing_exclusion_reason(db, product.id)
    assert serialize_listing_job_lite(db, job)["cancellation_scope"] == "publication_only"
    update_listing_job(db, job, status="queued")
    assert job.status == "cancelled"
    update_listing_job(db, job, status="cancelled")
    assert job.cancellation_scope == "product"
    assert stock_restoration_block(db, listing)


@pytest.mark.parametrize("guard", ["paused", "deleted", "relist", "stock", "price", "shipping", "stale", "missing_observation"])
def test_scoped_cancel_does_not_bypass_other_guards(records, guard):
    db, product, supplier, listing, job = records
    job.cancellation_scope = "publication_only"
    if guard in {"paused", "deleted"}: product.status = guard
    elif guard == "relist": listing.relist_blocked = True
    elif guard == "stock": supplier.in_stock = False
    elif guard == "price": supplier.last_price = None
    elif guard == "shipping": supplier.last_shipping = -1
    elif guard == "stale": supplier.stock_observed_at = datetime.utcnow() - timedelta(days=2)
    elif guard == "missing_observation": supplier.price_observed_at = None
    db.commit()
    assert stock_restoration_block(db, listing)


@pytest.mark.parametrize("payload", [{"cancellation_scope": "publication_only"}, {"status": "queued", "cancellation_scope": "publication_only"}, {"status": "cancelled", "cancellation_scope": "unknown"}])
def test_invalid_scope_requests_rejected(payload):
    with pytest.raises(ValidationError): ListingJobUpdate(**payload)


def test_additive_migration_defaults_existing_rows_to_product(monkeypatch):
    import app.main as main
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE listing_jobs (id INTEGER PRIMARY KEY, status VARCHAR(32))"))
        conn.execute(text("INSERT INTO listing_jobs VALUES (1, 'cancelled')"))
    monkeypatch.setattr(main, "engine", engine)
    main._ensure_lightweight_columns()
    main._ensure_lightweight_columns()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT cancellation_scope FROM listing_jobs")).scalar_one() == "product"
    engine.dispose()

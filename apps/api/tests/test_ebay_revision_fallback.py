from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.domain import EbayListing, EbayRevisionJob, Product, SupplierProduct
from app.services import ebay_revisions


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(ebay_revisions, "read_pricing_settings", lambda db: {"ebay_revision_execution_mode": "browser_fallback"})
    monkeypatch.setattr(ebay_revisions, "assert_ebay_browser_account_can_list", lambda db, account: None)
    with sessionmaker(bind=engine)() as session:
        session.add(Product(id=1, sku="FALLBACK-1", title="Plant food", status="monitoring"))
        session.add(EbayListing(id=1, product_id=1, listing_id="800123456789", account_id="test-seller", status="active", price=29.99, quantity=0))
        session.add(SupplierProduct(product_id=1, supplier="home_depot", source_url="https://example.com/item", last_price=10.0, last_shipping=0.0, in_stock=True, price_unavailable=False, updated_at=datetime.utcnow()))
        session.commit()
        yield session
    engine.dispose()


def add_job(db, action, status="queued"):
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=1,
        ebay_account_key="test-seller",
        action=action,
        target_price=29.99,
        status=status,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
        started_at=datetime.utcnow() if status == "running" else None,
        lease_expires_at=datetime.utcnow() + timedelta(minutes=10) if status == "running" else None,
        attempts=1 if status == "running" else 0,
    )
    db.add(job)
    db.commit()
    return job


@pytest.mark.parametrize("action", ["mark_out_of_stock", "restore_stock", "retire_zero_view", "retire_duplicate", "end_zero_view", "future_action"])
@pytest.mark.parametrize("status", ["queued", "running"])
def test_fallback_skips_unsupported_actions_without_mutating_them(db, action, status):
    unsupported = add_job(db, action, status)
    before = (unsupported.status, unsupported.attempts, unsupported.started_at, unsupported.lease_expires_at, unsupported.completed_at)

    assert ebay_revisions.start_next_ebay_revision_job(db) is None
    db.refresh(unsupported)
    assert (unsupported.status, unsupported.attempts, unsupported.started_at, unsupported.lease_expires_at, unsupported.completed_at) == before

    price = add_job(db, "revise_price")
    assert ebay_revisions.start_next_ebay_revision_job(db).id == price.id
    assert price.status == "running"
    assert price.attempts == 1
    db.refresh(unsupported)
    assert (unsupported.status, unsupported.attempts, unsupported.started_at, unsupported.lease_expires_at, unsupported.completed_at) == before


def test_fallback_reoffers_supported_running_price_before_queued_price(db):
    running = add_job(db, "revise_price", "running")
    queued = add_job(db, "revise_price")
    assert ebay_revisions.start_next_ebay_revision_job(db).id == running.id
    assert running.attempts == 1
    assert queued.status == "queued"

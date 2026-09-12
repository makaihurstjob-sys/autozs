"""Freshness-guard regressions for stock_restoration_block.

updated_at bumps on any metadata edit to SupplierProduct, not just genuine stock/price/
shipping observations (see docs/agents/supplier-freshness-followup.md). These tests pin
down that a positive restoration now requires each of stock_observed_at, price_observed_at
and shipping_observed_at to be independently present and within 24 hours -- with no
fallback to updated_at for rows that predate this feature.
"""
from datetime import datetime, timedelta

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.domain import EbayListing, Product, SupplierProduct
from app.services.ebay_revisions import stock_restoration_block


def make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def _restockable_listing_and_supplier(db, **observation_overrides):
    """A listing + supplier that pass every check except (possibly) freshness."""
    product = Product(sku="FRESH-1", title="Freshness test widget", status="monitoring")
    db.add(product)
    db.flush()
    now = datetime.utcnow()
    defaults = {
        "stock_observed_at": now,
        "price_observed_at": now,
        "shipping_observed_at": now,
    }
    defaults.update(observation_overrides)
    supplier = SupplierProduct(
        product_id=product.id,
        supplier="home_depot",
        source_url="https://www.homedepot.com/p/example/1",
        last_price=9.47,
        last_shipping=0.0,
        in_stock=True,
        price_unavailable=False,
        **defaults,
    )
    db.add(supplier)
    listing = EbayListing(
        product_id=product.id,
        listing_id="800123456789",
        account_id="a.m.anim-59",
        status="active",
        price=14.53,
        quantity=0,
    )
    db.add(listing)
    db.commit()
    return listing, supplier


def test_all_three_timestamps_fresh_allows_restoration() -> None:
    db = make_session()
    listing, _ = _restockable_listing_and_supplier(db)

    assert stock_restoration_block(db, listing) is None


def test_missing_stock_observed_at_blocks_restoration() -> None:
    db = make_session()
    listing, _ = _restockable_listing_and_supplier(db, stock_observed_at=None)

    reason = stock_restoration_block(db, listing)
    assert reason is not None
    assert "stock" in reason


def test_missing_price_observed_at_blocks_restoration() -> None:
    db = make_session()
    listing, _ = _restockable_listing_and_supplier(db, price_observed_at=None)

    reason = stock_restoration_block(db, listing)
    assert reason is not None
    assert "price" in reason


def test_missing_shipping_observed_at_blocks_restoration() -> None:
    db = make_session()
    listing, _ = _restockable_listing_and_supplier(db, shipping_observed_at=None)

    reason = stock_restoration_block(db, listing)
    assert reason is not None
    assert "shipping" in reason


def test_stale_stock_observed_at_blocks_restoration_even_with_other_two_fresh() -> None:
    db = make_session()
    stale = datetime.utcnow() - timedelta(hours=25)
    listing, _ = _restockable_listing_and_supplier(db, stock_observed_at=stale)

    reason = stock_restoration_block(db, listing)
    assert reason is not None
    assert "stock" in reason


def test_stale_price_observed_at_blocks_restoration_even_with_other_two_fresh() -> None:
    db = make_session()
    stale = datetime.utcnow() - timedelta(hours=25)
    listing, _ = _restockable_listing_and_supplier(db, price_observed_at=stale)

    reason = stock_restoration_block(db, listing)
    assert reason is not None
    assert "price" in reason


def test_stale_shipping_observed_at_blocks_restoration_even_with_other_two_fresh() -> None:
    db = make_session()
    stale = datetime.utcnow() - timedelta(hours=25)
    listing, _ = _restockable_listing_and_supplier(db, shipping_observed_at=stale)

    reason = stock_restoration_block(db, listing)
    assert reason is not None
    assert "shipping" in reason


def test_observation_exactly_at_the_24_hour_boundary_is_stale() -> None:
    """Guards against an off-by-one on the boundary: "within 24 hours" must not admit
    evidence that is exactly (or older than) 24 hours old, only strictly newer."""
    db = make_session()
    boundary = datetime.utcnow() - timedelta(hours=24)
    listing, _ = _restockable_listing_and_supplier(db, stock_observed_at=boundary)

    assert stock_restoration_block(db, listing) is not None


def test_legacy_row_with_all_three_timestamps_null_is_blocked_not_grandfathered() -> None:
    """A row migrated from before this feature has real supplier data (in_stock=True,
    a valid price and updated_at recently touched) but none of the three explicit
    observation timestamps. It must fail the freshness check, not be waved through
    because updated_at happens to look recent."""
    db = make_session()
    listing, supplier = _restockable_listing_and_supplier(
        db,
        stock_observed_at=None,
        price_observed_at=None,
        shipping_observed_at=None,
    )
    # Simulate the legacy-row shape: updated_at was bumped by an unrelated metadata
    # edit well within the last 24 hours, which must NOT be treated as evidence.
    supplier.updated_at = datetime.utcnow()
    db.commit()

    reason = stock_restoration_block(db, listing)
    assert reason is not None


def test_quantity_zero_reduction_path_is_unaffected_by_missing_observations() -> None:
    """stock_restoration_block only governs increasing quantity. Reducing to zero goes
    through supplier_availability_block instead and must still work with no observation
    timestamps at all -- otherwise a listing could never be marked out of stock."""
    from app.services.ebay_revisions import supplier_availability_block

    db = make_session()
    listing, supplier = _restockable_listing_and_supplier(
        db,
        stock_observed_at=None,
        price_observed_at=None,
        shipping_observed_at=None,
    )
    supplier.in_stock = False

    assert supplier_availability_block(supplier) == "the supplier reports it out of stock"


def test_recording_a_completed_restock_job_is_unaffected_by_evidence_expiring() -> None:
    """Once a restock job has already been approved and applied, recording that
    authoritative completed action must not be re-blocked by evidence going stale in
    the interim -- only the decision to *propose* a new restoration is guarded."""
    from app.models.domain import EbayRevisionJob, EbayRevisionJobStatus
    from app.services.ebay_revisions import RESTOCK_ACTION, update_ebay_revision_job

    db = make_session()
    listing, supplier = _restockable_listing_and_supplier(db)
    listing.quantity = 0
    job = EbayRevisionJob(
        product_id=listing.product_id,
        ebay_listing_id=listing.id,
        ebay_account_key=listing.account_id,
        action=RESTOCK_ACTION,
        target_price=listing.price,
        status=EbayRevisionJobStatus.running.value,
        guard_passed=True,
        approval_required=False,
    )
    db.add(job)
    db.commit()

    # Evidence goes stale after the job was already queued/running.
    supplier.stock_observed_at = datetime.utcnow() - timedelta(hours=25)
    db.commit()

    update_ebay_revision_job(db, job, status="completed")

    assert job.status == "completed"
    assert listing.quantity == 1

@pytest.mark.parametrize('field,value', [('last_price', value) for value in (0.0, -1.0, float('nan'), float('inf'), -float('inf'))] + [('last_shipping', value) for value in (float('nan'), float('inf'), -float('inf'))])
def test_invalid_numeric_values_block_restoration_with_fresh_timestamps(field, value):
    db = make_session()
    try:
        listing, supplier = _restockable_listing_and_supplier(db)
        setattr(supplier, field, value)
        assert stock_restoration_block(db, listing, supplier) is not None
    finally:
        db.close()

@pytest.mark.parametrize('field', ['stock_observed_at', 'price_observed_at', 'shipping_observed_at'])
def test_future_observations_block_restoration(field):
    db = make_session()
    try:
        listing, supplier = _restockable_listing_and_supplier(db, **{field: datetime.utcnow() + timedelta(hours=1)})
        assert stock_restoration_block(db, listing, supplier) is not None
    finally:
        db.close()

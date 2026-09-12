"""Tests for per-field supplier observation timestamps.

See docs/agents/supplier-freshness-followup.md and
docs/agents/supplier-observations.md for the background: SupplierProduct rows
never recorded *when* stock/price/shipping were actually observed from the
supplier, so a title-only or price-only capture could make stale stock data
look fresh to downstream restock logic. These tests exercise the fix:
stock_observed_at / price_observed_at / shipping_observed_at on
SupplierProduct, stamped only when a capture supplies explicit evidence for
that specific field.
"""

import time
from datetime import datetime

import pytest

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as app_main
from app.core.database import Base
from app.services import importer
from app.models.domain import EbayListing
from app.services.ebay_revisions import stock_restoration_block

# Small, real sleep between captures so successive datetime.utcnow() stamps are
# guaranteed to differ even on coarser Windows clock resolutions.
_TICK = 0.05


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def test_title_only_and_single_field_captures_do_not_cross_refresh_other_fields() -> None:
    db = _session()
    try:
        source_url = "https://www.homedepot.com/p/Isolation-Test/900001"
        product = importer.import_captured_product(
            db,
            source_url=source_url,
            title="Widget",
            source_price=9.99,
            source_shipping=2.50,
            source_in_stock=True,
        )
        supplier = product.supplier_products[0]
        stock_t1 = supplier.stock_observed_at
        price_t1 = supplier.price_observed_at
        shipping_t1 = supplier.shipping_observed_at
        assert stock_t1 is not None
        assert price_t1 is not None
        assert shipping_t1 is not None

        time.sleep(_TICK)
        product = importer.update_product_from_capture(db, product.id, title="Widget Pro")
        supplier = product.supplier_products[0]
        assert supplier.stock_observed_at == stock_t1
        assert supplier.price_observed_at == price_t1
        assert supplier.shipping_observed_at == shipping_t1

        time.sleep(_TICK)
        product = importer.update_product_from_capture(db, product.id, source_price=10.99)
        supplier = product.supplier_products[0]
        assert supplier.price_observed_at is not None and supplier.price_observed_at > price_t1
        # Price-only capture must not refresh stock or shipping evidence.
        assert supplier.stock_observed_at == stock_t1
        assert supplier.shipping_observed_at == shipping_t1
        price_t2 = supplier.price_observed_at

        time.sleep(_TICK)
        product = importer.update_product_from_capture(db, product.id, source_shipping=3.75)
        supplier = product.supplier_products[0]
        assert supplier.shipping_observed_at is not None and supplier.shipping_observed_at > shipping_t1
        # Shipping-only capture must not refresh stock or price evidence.
        assert supplier.stock_observed_at == stock_t1
        assert supplier.price_observed_at == price_t2
    finally:
        db.close()


def test_complete_explicit_capture_sets_all_three_observed_timestamps_to_now() -> None:
    db = _session()
    try:
        product = importer.import_captured_product(
            db,
            source_url="https://www.homedepot.com/p/Complete-Capture/900002",
            title="Complete Capture Widget",
            source_price=19.99,
            source_shipping=0.0,
            source_in_stock=True,
        )
        supplier = product.supplier_products[0]
        assert supplier.stock_observed_at is not None
        assert supplier.price_observed_at is not None
        assert supplier.shipping_observed_at is not None
        # One capture event shares a single server receipt time across fields.
        assert supplier.stock_observed_at == supplier.price_observed_at == supplier.shipping_observed_at
    finally:
        db.close()


def test_negative_stock_and_unavailable_price_recorded_immediately_not_resurrected_by_incomplete_capture() -> None:
    db = _session()
    try:
        product = importer.import_captured_product(
            db,
            source_url="https://www.homedepot.com/p/Goes-Stale/900003",
            title="Goes Stale Widget",
            source_price=14.5,
            source_shipping=1.25,
            source_in_stock=True,
        )
        supplier = product.supplier_products[0]
        assert supplier.in_stock is True

        time.sleep(_TICK)
        product = importer.update_product_from_capture(
            db,
            product.id,
            source_in_stock=False,
            source_price_unavailable=True,
        )
        supplier = product.supplier_products[0]
        assert supplier.in_stock is False
        assert supplier.price_unavailable is True
        assert supplier.last_shipping == -1.0
        stock_t2 = supplier.stock_observed_at
        price_t2 = supplier.price_observed_at
        assert stock_t2 is not None
        assert price_t2 is not None
        # Out-of-stock invalidates shipping immediately; it is not affirmative
        # shipping evidence, so the shipping observation is cleared.
        assert supplier.shipping_observed_at is None

        time.sleep(_TICK)
        product = importer.update_product_from_capture(db, product.id, title="Goes Stale Widget Renamed")
        supplier = product.supplier_products[0]
        # A subsequent incomplete (title-only) capture must not resurrect the
        # negative/unavailable evidence as if it were freshly observed again,
        # nor silently flip the recorded state back.
        assert supplier.in_stock is False
        assert supplier.price_unavailable is True
        assert supplier.stock_observed_at == stock_t2
        assert supplier.price_observed_at == price_t2
        assert supplier.shipping_observed_at is None
    finally:
        db.close()


def test_source_identity_change_clears_observations_but_unrelated_edit_does_not() -> None:
    db = _session()
    try:
        old_url = "https://www.homedepot.com/p/Old-Listing-Slug/900004"
        product = importer.import_captured_product(
            db,
            source_url=old_url,
            title="Relisted Widget",
            source_price=25.0,
            source_shipping=5.0,
            source_in_stock=True,
        )
        supplier = product.supplier_products[0]
        stock_t1 = supplier.stock_observed_at
        price_t1 = supplier.price_observed_at
        shipping_t1 = supplier.shipping_observed_at
        assert stock_t1 is not None and price_t1 is not None and shipping_t1 is not None

        time.sleep(_TICK)
        # Unrelated metadata edit on the *same* source must leave observation
        # evidence untouched.
        product = importer.update_product_from_capture(db, product.id, title="Relisted Widget (Renamed)")
        supplier = product.supplier_products[0]
        assert supplier.stock_observed_at == stock_t1
        assert supplier.price_observed_at == price_t1
        assert supplier.shipping_observed_at == shipping_t1

        time.sleep(_TICK)
        # Same physical Home Depot product (same trailing product id / stable
        # supplier sku), but a new source URL/listing slug -- a genuine source
        # identity change. No new price/shipping/stock evidence is supplied
        # (title-only), so nothing should be re-stamped either.
        new_url = "https://www.homedepot.com/p/New-Listing-Slug/900004"
        product = importer.import_captured_product(
            db,
            source_url=new_url,
            title="Relisted Widget (New Listing)",
        )
        supplier = product.supplier_products[0]
        assert supplier.source_url == new_url
        assert supplier.stock_observed_at is None
        assert supplier.price_observed_at is None
        assert supplier.shipping_observed_at is None
    finally:
        db.close()


def test_bulk_url_import_never_stamps_observation_timestamps(monkeypatch) -> None:
    db = _session()
    try:
        source_url = "https://example.com/product/bulk-item"

        def source_fetch(source: str, source_price_override=None) -> importer.ImportedProductData:
            return importer.ImportedProductData(
                source_url=source,
                supplier="source_site",
                supplier_sku="bulk-item",
                title="Bulk Item",
                source_price=12.34,
                description="Bulk item details",
                image_urls=[],
                warnings=[],
            )

        monkeypatch.setattr(importer, "extract_product_data", source_fetch)
        products, _warnings = importer.import_products(db, [source_url])

        supplier = products[0].supplier_products[0]
        assert supplier.in_stock is True
        assert supplier.last_price == 12.34
        # The bulk/URL importer's default in_stock=True is not an observation.
        assert supplier.stock_observed_at is None
        assert supplier.price_observed_at is None
        assert supplier.shipping_observed_at is None
    finally:
        db.close()


def test_migration_adds_columns_leaves_existing_rows_null_and_is_idempotent(monkeypatch) -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE supplier_products (
                    id INTEGER PRIMARY KEY,
                    product_id INTEGER NOT NULL,
                    supplier VARCHAR(64) NOT NULL DEFAULT 'home_depot',
                    source_url TEXT NOT NULL,
                    supplier_sku VARCHAR(128),
                    last_price FLOAT,
                    last_shipping FLOAT NOT NULL DEFAULT 0.0,
                    subscription_discount_percent FLOAT,
                    minimum_order_quantity INTEGER NOT NULL DEFAULT 1,
                    in_stock BOOLEAN NOT NULL DEFAULT 1,
                    price_unavailable BOOLEAN NOT NULL DEFAULT 0,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO supplier_products "
                "(id, product_id, supplier, source_url, last_price, in_stock) "
                "VALUES (1, 1, 'home_depot', 'https://www.homedepot.com/p/Legacy/1', 5.0, 1)"
            )
        )

    monkeypatch.setattr(app_main, "engine", engine)
    try:
        app_main._ensure_lightweight_columns()
        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("supplier_products")}
        assert {"stock_observed_at", "price_observed_at", "shipping_observed_at"} <= columns

        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT stock_observed_at, price_observed_at, shipping_observed_at "
                    "FROM supplier_products WHERE id = 1"
                )
            ).one()
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None

        # Running the migration step again must be a no-op, not an error.
        app_main._ensure_lightweight_columns()
        with engine.connect() as connection:
            row_again = connection.execute(
                text(
                    "SELECT stock_observed_at, price_observed_at, shipping_observed_at "
                    "FROM supplier_products WHERE id = 1"
                )
            ).one()
        assert row_again[0] is None
        assert row_again[1] is None
        assert row_again[2] is None
    finally:
        engine.dispose()


@pytest.mark.parametrize('price', [0.0, -1.0, float('nan'), float('inf'), -float('inf')])
def test_invalid_capture_clears_previous_price_evidence(price):
    db = _session()
    try:
        product = importer.import_captured_product(db, source_url='https://www.homedepot.com/p/Invalid/990001', title='Widget', source_price=10.0, source_shipping=0.0, source_in_stock=True)
        listing = EbayListing(product_id=product.id, listing_id='900001', status='active', price=20.0, quantity=0)
        db.add(listing)
        db.commit()
        supplier = product.supplier_products[0]
        assert stock_restoration_block(db, listing, supplier) is None
        importer._apply_supplier_capture(supplier, source_price=price, source_shipping=None, source_in_stock=None, source_price_unavailable=None, received_at=datetime.utcnow())
        assert supplier.price_observed_at is None
        assert stock_restoration_block(db, listing, supplier) is not None
    finally:
        db.close()

@pytest.mark.parametrize('shipping', [-1.0, float('nan'), float('inf'), -float('inf')])
def test_invalid_shipping_capture_clears_previous_evidence(shipping):
    supplier = importer.SupplierProduct(last_price=10.0, last_shipping=0.0, shipping_observed_at=datetime.utcnow())
    importer._apply_supplier_capture(supplier, source_price=None, source_shipping=shipping, source_in_stock=None, source_price_unavailable=None, received_at=datetime.utcnow())
    assert supplier.shipping_observed_at is None


def test_bulk_refresh_invalidates_overwritten_capture_evidence(monkeypatch):
    db = _session()
    try:
        url = 'https://www.homedepot.com/p/Bulk-Overwrite/990002'
        product = importer.import_captured_product(db, source_url=url, title='Widget', source_price=10.0, source_shipping=0.0, source_in_stock=True)
        monkeypatch.setattr(importer, 'extract_product_data', lambda source, source_price_override=None: importer.ImportedProductData(source_url=source, supplier='home_depot', supplier_sku='990002', title='Widget', source_price=0.0, description='', image_urls=[], warnings=[]))
        importer.import_products(db, [url], source_shipping_override=2.0)
        supplier = product.supplier_products[0]
        db.refresh(supplier)
        assert supplier.price_observed_at is None
        assert supplier.shipping_observed_at is None
        assert supplier.stock_observed_at is None
    finally:
        db.close()

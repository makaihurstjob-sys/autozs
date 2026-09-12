from datetime import datetime, timedelta

import pytest

from app.core.database import get_db
from app.main import app
from app.models.domain import EbayListing, ListingJob, SupplierProduct
from app.services.orders import _queue_replacement_publish
from app.services.listing_jobs import queue_zero_view_listing_rotations
from test_listing_jobs import create_ready_product


@pytest.mark.parametrize('flow', ['sale', 'rotation'])
@pytest.mark.parametrize('field', ['stock_observed_at', 'price_observed_at', 'shipping_observed_at'])
@pytest.mark.parametrize('evidence', ['missing', 'stale', 'fresh', 'future'])
def test_publish_requires_each_actual_observation(client, monkeypatch, flow, field, evidence):
    product_data = create_ready_product(client, source_id='freshness-replacement')
    client.patch('/settings/pricing', json={'auto_delist_zero_view_enabled': True,
                                           'auto_delist_zero_view_days': 29}).raise_for_status()
    db = next(app.dependency_overrides[get_db]())
    try:
        now = datetime.utcnow()
        supplier = db.query(SupplierProduct).one()
        supplier.in_stock = True
        supplier.price_unavailable = False
        # Old metadata does not invalidate current observations; new metadata
        # cannot rescue missing or stale observations.
        supplier.updated_at = now - timedelta(days=2) if evidence == 'fresh' else now
        for name in ('stock_observed_at', 'price_observed_at', 'shipping_observed_at'):
            setattr(supplier, name, now - timedelta(hours=1))
        setattr(supplier, field, {'missing': None, 'stale': now - timedelta(hours=25),
                                 'fresh': now - timedelta(hours=24),
                                 'future': now + timedelta(hours=1)}[evidence])
        if flow == 'rotation':
            old = create_ready_product(client, source_id='freshness-old')
            db.add(EbayListing(product_id=old['id'], listing_id='old-item', account_id='seller-a',
                               status='active', quantity=1, views=0, views_measured_at=now,
                               first_listed_at=now - timedelta(days=30)))
            monkeypatch.setattr('app.services.listing_jobs.ensure_checks', lambda *args: None)
            monkeypatch.setattr('app.services.listing_jobs.build_listing_readiness', lambda *args: {'manual_ready': True})
            monkeypatch.setattr('app.services.listing_jobs.build_ebay_listing_package', lambda *args: {'meets_minimum_profit': True})
        db.commit()
        if flow == 'sale':
            result = _queue_replacement_publish(db, product=supplier.product, account_key='seller-a',
                                                now=now, require_confirmed_stock=True)
        else:
            result = queue_zero_view_listing_rotations(db, ebay_account_key='seller-a', limit=1, now=now)['queued']
        assert bool(result) == (evidence == 'fresh')
        db.flush()
        assert [job.ebay_account_key for job in db.query(ListingJob).all()] == (['seller-a'] if evidence == 'fresh' else [])
    finally:
        db.close()


@pytest.mark.parametrize('flow', ['sale', 'rotation'])
@pytest.mark.parametrize('field,value,allowed', [
    ('last_price', 0.0, False), ('last_price', -1.0, False),
    ('last_price', float('inf'), False), ('last_price', float('-inf'), False),
    ('last_shipping', -1.0, False), ('last_shipping', float('inf'), False),
    ('last_shipping', float('-inf'), False), ('last_shipping', 0.0, True),
])
def test_publish_rejects_persisted_invalid_costs(client, monkeypatch, flow, field, value, allowed):
    create_ready_product(client, source_id='numeric-replacement')
    client.patch('/settings/pricing', json={'auto_delist_zero_view_enabled': True,
                                           'auto_delist_zero_view_days': 29}).raise_for_status()
    db = next(app.dependency_overrides[get_db]())
    try:
        now = datetime.utcnow()
        supplier = db.query(SupplierProduct).one()
        supplier_id = supplier.id
        for name in ('stock_observed_at', 'price_observed_at', 'shipping_observed_at'):
            setattr(supplier, name, now - timedelta(hours=1))
        setattr(supplier, field, value)
        if flow == 'rotation':
            old = create_ready_product(client, source_id='numeric-old')
            db.add(EbayListing(product_id=old['id'], listing_id='old-item', account_id='seller-a',
                               status='active', quantity=1, views=0, views_measured_at=now,
                               first_listed_at=now - timedelta(days=30)))
            monkeypatch.setattr('app.services.listing_jobs.ensure_checks', lambda *args: None)
            monkeypatch.setattr('app.services.listing_jobs.build_listing_readiness', lambda *args: {'manual_ready': True})
            monkeypatch.setattr('app.services.listing_jobs.build_ebay_listing_package', lambda *args: {'meets_minimum_profit': True})
        db.commit()
        db.expire_all()
        supplier = db.get(SupplierProduct, supplier_id)
        assert getattr(supplier, field) == value  # Exercise actual persisted infinity, not just ORM state.
        if flow == 'sale':
            result = _queue_replacement_publish(db, product=supplier.product, account_key='seller-a',
                                                now=now, require_confirmed_stock=True)
        else:
            result = queue_zero_view_listing_rotations(db, ebay_account_key='seller-a', limit=1, now=now)['queued']
        assert bool(result) == allowed
        db.flush()
        assert db.query(ListingJob).count() == int(allowed)
    finally:
        db.close()


@pytest.mark.parametrize('flow', ['sale', 'rotation'])
@pytest.mark.parametrize('field', ['last_price', 'last_shipping'])
def test_nan_rejected_before_sqlite_can_coerce_it(client, field, flow):
    import math
    create_ready_product(client, source_id='numeric-nan')
    db = next(app.dependency_overrides[get_db]())
    try:
        supplier = db.query(SupplierProduct).one()
        setattr(supplier, field, float('nan'))
        # No flush: sqlite3 converts NaN to SQL NULL (shipping is NOT NULL).
        assert math.isnan(getattr(supplier, field))
        if flow == 'sale':
            assert not _queue_replacement_publish(db, product=supplier.product, account_key='seller-a',
                                                  now=datetime.utcnow(), require_confirmed_stock=True)
        else:
            from app.services.listing_jobs import _supplier_delivery_unavailable
            assert _supplier_delivery_unavailable(supplier.product)
        assert not any(isinstance(row, ListingJob) for row in db.new)
    finally:
        db.rollback()
        db.close()

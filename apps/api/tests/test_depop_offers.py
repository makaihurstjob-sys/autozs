from app.services.depop_offers import offer_floor, variant_offer_plan
from test_depop_scheduling import db, seed
import pytest


def test_rounding_and_boost_tax_shipping_fees_preserve_net_margin():
    plan = offer_floor(landed_cost_cap=19.99, seller_shipping_cap=4.1,
        processing_extra_base_cap=12, boost_extra_base_cap=0, listed_price=49.98)
    assert plan['enabled']
    assert plan['net_margin'] >= .25
    assert plan['offer_price'] < 49.98


def test_expensive_product_gets_no_discount():
    assert not offer_floor(landed_cost_cap=30, seller_shipping_cap=10,
        processing_extra_base_cap=12, boost_extra_base_cap=5, listed_price=39.98)['enabled']


@pytest.mark.parametrize('bad', [-1, float('nan'), float('inf')])
def test_invalid_costs_do_not_authorize_an_offer(bad):
    with pytest.raises(ValueError):
        offer_floor(landed_cost_cap=bad, seller_shipping_cap=0,
            processing_extra_base_cap=0, boost_extra_base_cap=0, listed_price=30)


def test_missing_cost_evidence_blocks_active_listing(db):
    variant = seed(db)
    variant.depop_listing_id = 'closet-test'; variant.status = 'published'; db.commit()
    assert not variant_offer_plan(db, variant.id)['enabled']


def test_cost_evidence_route_persists_only_valid_bounded_evidence(db):
    from app.api.routes import depop_offer_cost_evidence
    from datetime import datetime, timedelta, timezone
    variant = seed(db)
    variant.depop_listing_id = 'closet-test'; variant.status = 'published'; db.commit()
    now = datetime.now(timezone.utc)
    payload = dict(account_key='closet', currency='USD', landed_cost_cap=5,
        seller_shipping_cap=0, processing_extra_base_cap=10, boost_extra_base_cap=0,
        observed_at=(now-timedelta(seconds=1)).isoformat(), expires_at=(now+timedelta(hours=1)).isoformat(),
        evidence_url='https://supplier.test/cart-quote', includes_supplier_tax_and_shipping=True)
    result = depop_offer_cost_evidence(variant.id, payload, db)
    assert result['enabled'] and result['net_margin'] >= .25


def test_stale_cost_evidence_cannot_enable_offers(db):
    import json
    from datetime import datetime, timedelta, timezone
    from app.models.domain import AppSetting
    variant=seed(db); variant.depop_listing_id='closet-test'; variant.status='published'; db.flush()
    now=datetime.now(timezone.utc)
    db.add(AppSetting(key=f'depop_offer_cost:{variant.id}',value=json.dumps({
        'observed_at':(now-timedelta(hours=7)).isoformat(), 'expires_at':(now+timedelta(hours=1)).isoformat(),
        'currency':'USD','account_key':'closet','evidence_url':'https://supplier.test/cart',
        'landed_cost_cap':5,'seller_shipping_cap':0,'processing_extra_base_cap':10,'boost_extra_base_cap':0})))
    db.commit()
    assert not variant_offer_plan(db,variant.id)['enabled']

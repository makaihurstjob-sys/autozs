"""Offer floors from explicit, current landed-cost and fee-base evidence."""
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING

from sqlalchemy import select
from app.models.domain import AppSetting
from app.models.depop import DepopListingVariant

D = lambda value: Decimal(str(value))
CENT = Decimal('0.01')


def offer_floor(*, landed_cost_cap, seller_shipping_cap, processing_extra_base_cap,
                boost_extra_base_cap, listed_price):
    values = [D(x) for x in (landed_cost_cap, seller_shipping_cap,
                             processing_extra_base_cap, boost_extra_base_cap, listed_price)]
    if any(not x.is_finite() or x < 0 for x in values) or values[-1] <= 0:
        raise ValueError('Finite, nonnegative, verified costs and positive price required')
    cost, shipping, extra, boost_extra, price = values
    # US official fee schedule checked 2026-10-18. Reserve Boost even on organic sales.
    floor = ((cost + shipping + D('.45') + D('.033') * extra + D('.12') * boost_extra)
             / (1 - D('.033') - D('.12') - D('.25'))).quantize(CENT, rounding=ROUND_CEILING)
    proposed = max(floor, (price * D('.90')).quantize(CENT, rounding=ROUND_CEILING))
    # Round each percentage fee upward and re-check the actual resulting margin.
    while proposed < price:
        processing = ((proposed + extra) * D('.033')).quantize(CENT, rounding=ROUND_CEILING) + D('.45')
        boost = ((proposed + boost_extra) * D('.12')).quantize(CENT, rounding=ROUND_CEILING)
        profit = proposed - cost - shipping - processing - boost
        if profit / proposed >= D('.25'):
            return {'enabled': True, 'minimum_offer_price': float(proposed),
                    'offer_price': float(proposed), 'net_margin': float(profit / proposed),
                    'profit': float(profit), 'minimum_margin': .25}
        proposed += CENT
    return {'enabled': False, 'reason': 'No discounted offer preserves 25% net margin.', 'minimum_margin': .25}


def variant_offer_plan(db, variant_id):
    variant = db.get(DepopListingVariant, variant_id)
    blocked = {'enabled': False, 'minimum_margin': .25, 'variant_id': variant_id}
    if variant is None or not variant.depop_listing_id or variant.status not in {'published', 'active'}:
        return {**blocked, 'reason': 'A confirmed active listing is required.'}
    row = db.scalar(select(AppSetting).where(AppSetting.key == f'depop_offer_cost:{variant_id}'))
    if row is None:
        return {**blocked, 'reason': 'Verified landed cost, seller shipping and processing tax/shipping bounds are missing; no offer authorized.'}
    try:
        evidence = json.loads(row.value)
        observed = datetime.fromisoformat(evidence['observed_at']).astimezone(timezone.utc)
        expiry = datetime.fromisoformat(evidence['expires_at']).astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if not observed <= now < expiry or (now - observed).total_seconds() > 21600:
            raise ValueError('stale')
        if evidence['currency'] != 'USD' or not evidence['evidence_url'] or evidence['account_key'] != variant.account_key:
            raise ValueError('unverified')
        plan = offer_floor(**{k: evidence[k] for k in ('landed_cost_cap', 'seller_shipping_cap',
            'processing_extra_base_cap', 'boost_extra_base_cap')}, listed_price=variant.price)
        return {**plan, 'variant_id': variant_id, 'listing_id': variant.depop_listing_id,
                'account_key': variant.account_key, 'listed_price': variant.price,
                'evidence_expires_at': expiry.isoformat()}
    except (ValueError, KeyError, TypeError, ArithmeticError):
        return {**blocked, 'reason': 'Cost evidence is missing, invalid or stale; no offer authorized.'}

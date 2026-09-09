"""Renewal-based pruning and a conservative calendar-month insertion budget."""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import AppSetting, EbayListing, EbayRevisionJob, ListingJob

POLICY_KEY = 'ebay_renewal_policy_enabled'
END_ACTION = 'end_zero_view'
ACTIVE = {'active', 'live', 'listed', 'scheduled'}
PRUNE_LEAD = timedelta(hours=2)
FRESH_VIEWS = timedelta(hours=2)


def enabled(db: Session) -> bool:
    row = db.scalar(select(AppSetting).where(AppSetting.key == POLICY_KEY))
    return bool(row and row.value.lower() == 'true')


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    local = utc(now).astimezone(ZoneInfo('America/Los_Angeles'))
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def pruning_reason(listing: EbayListing, now: datetime) -> str | None:
    now = utc(now)
    if listing.status not in ACTIVE or listing.status == 'scheduled' or listing.views != 0:
        return None
    if not listing.views_measured_at or not now - FRESH_VIEWS <= utc(listing.views_measured_at) <= now:
        return None
    if listing.relist_blocked and listing.removal_reason == 'zero_views_29_days':
        return 'Permanently end a previously zero-stock-pruned listing; zero views rechecked.'
    if listing.relist_blocked or not listing.renews_at:
        return None
    if now < utc(listing.renews_at) <= now + PRUNE_LEAD:
        return 'Zero views rechecked within two hours of the actual eBay renewal deadline.'
    return None


def queue_pruning(db: Session, account: str, limit: int = 15, now: datetime | None = None) -> dict:
    from app.services.ebay_revisions import _stock_job_fields
    now = now or datetime.now(timezone.utc)
    jobs = []
    for listing in db.scalars(select(EbayListing).where(EbayListing.account_id == account).order_by(EbayListing.renews_at.asc())).all():
        reason = pruning_reason(listing, now)
        if not reason:
            continue
        existing = db.scalar(select(EbayRevisionJob.id).where(
            EbayRevisionJob.ebay_listing_id == listing.id, EbayRevisionJob.action == END_ACTION,
            EbayRevisionJob.status.in_({'queued', 'running', 'needs_review', 'paused', 'completed'})))
        if existing:
            continue
        job = EbayRevisionJob(product_id=listing.product_id, ebay_listing_id=listing.id,
            ebay_account_key=account, action=END_ACTION, old_price=listing.price,
            target_price=float(listing.price or 0), guard_reason=reason, message=reason,
            **_stock_job_fields(listing, None))
        db.add(job)
        jobs.append(job)
        if len(jobs) >= limit:
            break
    db.commit()
    return {'eligible': len(jobs), 'queued': len(jobs), 'replacements_ready': 0, 'pairs': [],
            'mode': 'end_before_renewal', 'lead_hours': 2, 'job_ids': [job.id for job in jobs]}


def budget_status(db: Session, account: str, now: datetime | None = None, exclude_job_id: int | None = None) -> dict:
    now = utc(now or datetime.now(timezone.utc))
    start, end = month_bounds(now)
    result = {'enabled': enabled(db), 'period_start': start.isoformat(), 'period_end': end.isoformat(),
              'can_publish': False, 'available': 0, 'reason': 'Verified eBay monthly allowance is required.'}
    row = db.scalar(select(AppSetting).where(AppSetting.key == f'ebay_allowance:{account}'))
    try:
        snapshot = json.loads(row.value) if row else {}
        observed = utc(datetime.fromisoformat(snapshot['observed_at']))
        if not start <= observed <= now or now - observed > timedelta(hours=6):
            raise ValueError('stale')
        if utc(datetime.fromisoformat(snapshot['period_start'])) != start:
            raise ValueError('wrong month')
        total, used = snapshot['total'], snapshot['used']
        if type(total) is not int or type(used) is not int or total < 0 or used < 0:
            raise ValueError('invalid counters')
    except (ValueError, KeyError, TypeError):
        return result
    # Reserve even quantity-zero listings until eBay confirms they ended.
    listings = db.scalars(select(EbayListing).where(EbayListing.account_id == account, EbayListing.status.in_(ACTIVE))).all()
    renewals = sum(1 for listing in listings if not listing.renews_at or utc(listing.renews_at) < start or observed <= utc(listing.renews_at) < end)
    jobs = db.scalars(select(ListingJob).where(ListingJob.ebay_account_key == account, ListingJob.action == 'publish')).all()
    committed_products = {listing.product_id for listing in listings}
    pending = 0
    completed_since = 0
    for job in jobs:
        if job.id == exclude_job_id:
            continue
        if job.status == 'completed' and job.completed_at and utc(job.completed_at) > observed:
            completed_since += 1
        elif job.status in {'queued', 'running', 'ready_to_save'} and job.product_id not in committed_products:
            scheduled = (job.listing_schedule_at.replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
                         if job.listing_schedule_at else now)
            if scheduled < end:
                pending += 1
    buffer = 5
    available = max(0, total - used - renewals - pending - completed_since - buffer)
    result.update(total=total, used=used, reserved_renewals=renewals, reserved_jobs=pending,
        completed_since_snapshot=completed_since, safety_buffer=buffer, available=available,
        can_publish=available > 0, observed_at=observed.isoformat(),
        reason='' if available else 'Monthly allowance is reserved for renewals and queued listings.')
    return result


def publish_block_reason(db: Session, job: ListingJob) -> str | None:
    if not enabled(db) or job.action != 'publish':
        return None
    now = datetime.now(timezone.utc)
    start, end = month_bounds(now)
    if job.listing_schedule_at:
        scheduled = job.listing_schedule_at.replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
        if scheduled >= end:
            return 'Next-month publishing requires that month’s verified allowance.'
    budget = budget_status(db, job.ebay_account_key, now, exclude_job_id=job.id)
    return None if budget['can_publish'] else budget['reason']


def save_allowance_snapshot(db: Session, account: str, payload: dict) -> dict:
    from urllib.parse import urlparse
    now = datetime.now(timezone.utc)
    start, end = month_bounds(now)
    total, used = payload.get('total'), payload.get('used')
    source = urlparse(str(payload.get('source_url', '')))
    if source.scheme != 'https' or source.hostname != 'www.ebay.com' or not source.path.startswith('/sh/'):
        raise ValueError('Snapshot must come from eBay Seller Hub.')
    if type(total) is not int or type(used) is not int or not 0 <= used <= total <= 100000:
        raise ValueError('Invalid free-listing allowance counters.')
    if payload.get('period_start') != start.isoformat() or payload.get('period_end') != end.isoformat():
        raise ValueError('Snapshot must explicitly match the current Pacific calendar month.')
    observed = utc(datetime.fromisoformat(payload['observed_at']))
    if not now - timedelta(minutes=5) <= observed <= now:
        raise ValueError('Capture a fresh eBay allowance reading first.')
    row = db.scalar(select(AppSetting).where(AppSetting.key == f'ebay_allowance:{account}'))
    if row is None:
        row = AppSetting(key=f'ebay_allowance:{account}', value='{}')
        db.add(row)
    row.value = json.dumps({**payload, 'observed_at': observed.isoformat()})
    db.commit()
    return budget_status(db, account)

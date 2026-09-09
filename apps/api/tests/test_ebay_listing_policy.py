import csv
import json
from datetime import datetime, timedelta, timezone
from io import StringIO

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.domain import AppSetting, EbayListing, EbayRevisionBatch, EbayRevisionJob, ListingJob, Product
from app.services.ebay_listing_policy import (POLICY_KEY, END_ACTION, budget_status, month_bounds,
    pruning_reason, queue_pruning, save_allowance_snapshot)
from app.services.ebay_revision_csv import build_ebay_price_revision_csv
from app.services.ebay_revision_batches import import_ebay_revision_result


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(AppSetting(key=POLICY_KEY, value='true'))
        session.add(Product(id=1, sku='TEST', title='Test product'))
        session.commit()
        yield session


def listing(db, **overrides):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    values = dict(product_id=1, listing_id='800123456789', account_id='test', status='active',
                  quantity=1, views=0, views_measured_at=now, renews_at=now+timedelta(hours=1), price=20)
    values.update(overrides)
    row = EbayListing(**values)
    db.add(row); db.commit()
    return row


def snapshot(db, total=250, used=0):
    now = datetime.now(timezone.utc)
    start,end = month_bounds(now)
    return save_allowance_snapshot(db,'test',dict(total=total,used=used,observed_at=now.isoformat(),
        period_start=start.isoformat(),period_end=end.isoformat(),source_url='https://www.ebay.com/sh/ovw'))


def test_pruning_uses_actual_renewal_and_fresh_views(db):
    row=listing(db)
    now=datetime.now(timezone.utc)
    assert pruning_reason(row,now)
    row.renews_at=now+timedelta(days=1)
    assert not pruning_reason(row,now)
    row.renews_at=now+timedelta(minutes=30); row.views=1
    assert not pruning_reason(row,now)
    row.views=0; row.views_measured_at=now-timedelta(hours=3)
    assert not pruning_reason(row,now)
    row.views_measured_at=now; row.renews_at=None
    assert not pruning_reason(row,now)


def test_legacy_cleanup_excludes_supplier_stock_shortages(db):
    row=listing(db,quantity=0,renews_at=None,relist_blocked=False)
    assert not pruning_reason(row,datetime.now(timezone.utc))
    row.relist_blocked=True;row.removal_reason='zero_views_29_days'
    assert pruning_reason(row,datetime.now(timezone.utc))
    assert queue_pruning(db,'test')['queued']==1
    assert queue_pruning(db,'test')['queued']==0


def test_end_csv_and_explicit_result_required(db):
    row=listing(db)
    ids=queue_pruning(db,'test')['job_ids']
    content,_=build_ebay_price_revision_csv(db,account_key='test',job_ids=ids,
        template_csv='Action,Item number,Start price,Available quantity\n')
    result=list(csv.DictReader(StringIO(content.lstrip('\ufeff'))))[0]
    assert result=={'Action':'End','Item number':'800123456789','Start price':'','Available quantity':'','EndCode':'NotAvailable'}
    batch=EbayRevisionBatch(account_key='test',job_ids_json=json.dumps(ids),filename='end.csv',csv_content=content)
    db.add(batch);db.commit()
    import_ebay_revision_result(db,batch,result_csv='Item number,Status\n800123456789,\n')
    assert row.status=='active'
    import_ebay_revision_result(db,batch,result_csv='Item number,Action,Status\n800123456789,End,Success\n')
    assert row.status=='ended' and row.relist_blocked and row.quantity==0


def test_csv_rechecks_views(db):
    row=listing(db);ids=queue_pruning(db,'test')['job_ids'];row.views=1;db.commit()
    with pytest.raises(ValueError,match='fresh zero-view'):
        build_ebay_price_revision_csv(db,account_key='test',job_ids=ids,template_csv='Action,Item number,Start price\n')


def test_budget_reserves_zero_quantity_renewals_and_queue(db):
    row=listing(db,quantity=0)
    snapshot(db,used=240)
    db.add(ListingJob(product_id=2,ebay_account_key='test',action='publish',status='queued'))
    db.commit()
    result=budget_status(db,'test')
    assert result['reserved_renewals']==1 and result['reserved_jobs']==1
    assert result['available']==3
    row.status='ended';db.commit()
    assert budget_status(db,'test')['used']==240
    assert budget_status(db,'test')['available']==4


def test_unknown_and_stale_budget_block_direct_claim(db):
    from app.services.listing_jobs import start_listing_job
    job=ListingJob(product_id=1,ebay_account_key='test',action='publish',status='queued')
    db.add(job);db.commit()
    assert not budget_status(db,'test')['can_publish']
    assert start_listing_job(db,job).status=='queued'
    assert 'allowance' in job.message
    snapshot(db)
    assert budget_status(db,'test')['can_publish']
    assert not budget_status(db,'test',datetime.now(timezone.utc)+timedelta(hours=7))['can_publish']


def test_month_boundary_is_pacific_not_utc():
    start,end=month_bounds(datetime(2026,10,1,2,tzinfo=timezone.utc))
    assert start==datetime(2026,9,1,7,tzinfo=timezone.utc)
    assert end==datetime(2026,10,1,7,tzinfo=timezone.utc)


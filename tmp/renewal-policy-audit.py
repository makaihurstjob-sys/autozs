import sys,json,collections
from datetime import datetime,timezone
sys.path.insert(0,'C:/AutoZS/repo/apps/api')
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from app.models.domain import EbayListing
from app.services.ebay_listing_policy import pruning_reason
with Session(create_engine('sqlite:///C:/AutoZS/data/autozs.db')) as db:
 rows=db.scalars(select(EbayListing).where(EbayListing.account_id=='a.m.anim-59',EbayListing.status=='active')).all()
 now=datetime.now(timezone.utc)
 print('active',len(rows),'missing renewal',sum(r.renews_at is None for r in rows))
 legacy=[r for r in rows if r.removal_reason=='zero_views_29_days']
 print('legacy',len(legacy),'view refresh range',str(min((r.views_measured_at for r in legacy if r.views_measured_at),default=None)),str(max((r.views_measured_at for r in legacy if r.views_measured_at),default=None)))
 candidates=[dict(id=r.id,item=r.listing_id,product=r.product_id,renewal=str(r.renews_at),views=r.views,reason=pruning_reason(r,now)) for r in rows if pruning_reason(r,now)]
 print('candidates',json.dumps(candidates))

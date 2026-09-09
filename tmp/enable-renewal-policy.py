import sys
sys.path.insert(0, 'C:/AutoZS/repo/apps/api')
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.domain import AppSetting
from app.services.ebay_listing_policy import POLICY_KEY
with Session(create_engine('sqlite:///C:/AutoZS/data/autozs.db')) as db:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == POLICY_KEY))
    if setting is None:
        setting = AppSetting(key=POLICY_KEY, value='true')
        db.add(setting)
    else:
        setting.value = 'true'
    db.commit()
    print('Renewal policy enabled; publishing pause unchanged.')

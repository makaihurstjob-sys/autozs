from copy import deepcopy
import pytest
from app.main import app
from app.core.database import get_db
from app.models.domain import EbayAccount, AppSetting
from app.services.ebay_payments import classify


def row(kind, uid, description, amount, fees, net, **extra):
    return dict(date='Sep 4, 2026', description=description, detail_url=f'https://www.ebay.com/mes/transactiondetails?type={kind}&uuid={uid}', amount=amount, fees=fees, net=net, **extra)


def test_refunds_and_payout_reversals_do_not_create_income():
    refund=row('REFUND','REFUND_1','Refund for order number 13-14947-26719','-$5.53','$1.12','-$4.41')
    assert classify(refund)['effect'] == -4.41
    payout=row('PAYOUT','SCHEDULED_PAYOUT__123','Payout 123','-','-','-$22.27',express_fee='$2.00 Express payout fee')
    credit=row('OTHER_FEE','PAYOUT_FEE_CREDIT__123','Payout fee credit','-','$2.00','$2.00')
    reversal=row('PAYOUT_CREDIT','PAYOUT_AUTO_CREDIT__123','Payout credit for payout 123','$20.27','-','$20.27')
    assert sum(classify(r)['effect'] for r in [payout,credit,reversal]) == 0
    with pytest.raises(ValueError): classify({**refund,'net':'-$5.53'})


def test_snapshot_retries_and_incomplete_capture(client):
    db=next(app.dependency_overrides[get_db]())
    db.add(EbayAccount(key='seller',label='Seller',account_id='seller'))
    db.commit()
    payload=dict(account_key='seller',source_url='https://www.ebay.com/mes/transactionlist?sh=true',filters=['STATUS_FILTER_ALL_STATUS','TYPE_FILTER_ALL_TYPES','DATE_FILTER_LAST_90_DAYS'],hide_listing_fees=False,search='',start_date='June 12, 2026',end_date='September 10, 2026',count=1,rows=[row('REFUND','REFUND_1','Refund for order number 13-14947-26719','-$5.53','$1.12','-$4.41')])
    for _ in range(2):
        r=client.post('/finance/ebay-payments/capture',json=payload)
        assert r.status_code==200,r.text
    assert db.query(AppSetting).filter(AppSetting.key.like('ebay_payment_evidence:%')).count()==1
    for updates in [{'count':2},{'hide_listing_fees':True},{'account_key':'wrong'},{'search':'filtered'},{'rows':payload['rows']*2,'count':2}]:
        assert client.post('/finance/ebay-payments/capture',json={**payload,**updates}).status_code==422
    report=client.get('/finance/overview').json()['profitability']['payments'][0]
    assert len(report['rows'])==1
    assert report['tracked_contribution_after_adjustments'] is None
    assert report['untracked_order_settlements']['13-14947-26719']==-4.41
    db.close()


def test_tracked_refund_adjustment_does_not_repeat_sale_fees(client):
    from types import SimpleNamespace
    from app.services.ebay_payments import capture, report, record_failure
    db=next(app.dependency_overrides[get_db]())
    db.add(EbayAccount(key='seller',label='Seller',account_id='seller'))
    db.commit()
    order_id='13-14947-26719'
    payload=dict(account_key='seller',source_url='https://www.ebay.com/mes/transactionlist',filters=['STATUS_FILTER_ALL_STATUS','TYPE_FILTER_ALL_TYPES','DATE_FILTER_LAST_90_DAYS'],hide_listing_fees=False,search='',start_date='June 12, 2026',end_date='September 10, 2026',count=2,rows=[row('ORDER','CAPTURE__'+order_id,'Order '+order_id,'$5.53','-$1.12','$4.41'),row('REFUND','REFUND_1','Refund for order number '+order_id,'-$5.53','$1.12','-$4.41')])
    capture(db,payload)
    profit=[dict(ebay_order_id=order_id,contribution=2.41,revenue=5.53,ebay_fees=1.12)]
    orders=[SimpleNamespace(ebay_order_id=order_id,account_id='seller')]
    result=report(db,profit,orders,[])[0]
    assert result['tracked_contribution_after_adjustments']==-2.0
    record_failure(db,'seller','Additional pages require review')
    result=report(db,profit,orders,[])[0]
    assert result['tracked_contribution_after_adjustments'] is None
    assert len(result['rows'])==2
    db.close()

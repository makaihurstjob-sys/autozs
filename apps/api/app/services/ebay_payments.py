"""Browser-observed eBay transactions; transfers never count as earnings."""
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlparse, parse_qs
from sqlalchemy import select
from app.models.domain import AppSetting, EbayAccount

PREFIX = 'ebay_payment_snapshot:'


def money(value):
    if value == '-':
        return Decimal(0)
    if not isinstance(value, str) or not re.fullmatch(r'-?\$[0-9,]+\.[0-9]{2}', value):
        raise ValueError('Missing or ambiguous transaction amount.')
    return Decimal(value.replace('$', '').replace(',', ''))


def classify(row):
    url = urlparse(row.get('detail_url', ''))
    query = parse_qs(url.query)
    if url.scheme != 'https' or url.hostname != 'www.ebay.com' or url.path != '/mes/transactiondetails':
        raise ValueError('Invalid transaction evidence URL.')
    uid = query.get('uuid', [''])[0]
    kind = query.get('type', [''])[0]
    if not uid or len(uid) > 256:
        raise ValueError('Transaction has no stable identity.')
    date = datetime.strptime(row['date'], '%b %d, %Y').strftime('%Y-%m-%d')
    amount, fees, net = [money(row.get(field)) for field in ['amount', 'fees', 'net']]
    description = str(row.get('description', ''))
    order_match = re.fullmatch(r'(?:Order |Refund for order number )(\d{2}-\d{5}-\d{5})', description)
    effect = Decimal(0)
    category = 'unsupported'
    if kind in {'ORDER', 'REFUND'} and order_match:
        if amount + fees != net:
            raise ValueError('Transaction revenue, fees and net do not balance.')
        if kind == 'ORDER' and (amount < 0 or fees > 0 or uid != 'CAPTURE__' + order_match[1]):
            raise ValueError('Sale identity or amounts do not reconcile.')
        if kind == 'REFUND' and (amount > 0 or fees < 0 or net > 0):
            raise ValueError('Refund amounts do not reconcile.')
        category = 'sale' if kind == 'ORDER' else 'refund'
        effect = net
    elif kind == 'PAYOUT' and uid.startswith('SCHEDULED_PAYOUT__'):
        if amount != 0 or fees != 0 or net > 0:
            raise ValueError('Unsupported payout breakdown.')
        category = 'transfer'
        extra = row.get('express_fee')
        if extra:
            match = re.fullmatch(r'(\$[0-9,]+\.[0-9]{2}) Express payout fee', extra)
            if not match:
                raise ValueError('Unsupported payout fee.')
            effect = -money(match[1])
            if abs(effect) > abs(net):
                raise ValueError('Payout fee exceeds payout.')
            category = 'payout_fee'
    elif kind == 'PAYOUT_CREDIT' and uid.startswith('PAYOUT_AUTO_CREDIT__'):
        if fees != 0 or amount != net or net < 0:
            raise ValueError('Payout reversal does not reconcile.')
        category = 'transfer'
    elif kind == 'OTHER_FEE' and uid.startswith('PAYOUT_FEE_CREDIT__') and description == 'Payout fee credit':
        if amount != 0 or fees != net or net < 0:
            raise ValueError('Payout fee credit does not reconcile.')
        category, effect = 'fee_credit', net
    return {'id': uid, 'date': date, 'category': category, 'order_id': order_match[1] if order_match else None,
            'effect': float(effect), 'amount': float(amount), 'fees': float(fees), 'net': float(net),
            'description': description, 'detail_url': row['detail_url']}


def capture(db, payload):
    account = str(payload.get('account_key', ''))
    if not db.scalar(select(EbayAccount).where(EbayAccount.key == account)):
        raise ValueError('Unknown seller account.')
    source = urlparse(payload.get('source_url', ''))
    if source.scheme != 'https' or source.hostname != 'www.ebay.com' or source.path != '/mes/transactionlist':
        raise ValueError('Not an eBay transaction list.')
    if payload.get('filters') != ['STATUS_FILTER_ALL_STATUS', 'TYPE_FILTER_ALL_TYPES', 'DATE_FILTER_LAST_90_DAYS'] or payload.get('hide_listing_fees') is not False or payload.get('search') != '':
        raise ValueError('Unfiltered transactions with listing fees visible are required.')
    rows = payload.get('rows', [])
    count = payload.get('count')
    if not rows or not isinstance(count, int) or count != len(rows) or count > 50:
        raise ValueError('Incomplete or paginated transaction list; review required.')
    start = datetime.strptime(payload['start_date'], '%B %d, %Y')
    end = datetime.strptime(payload['end_date'], '%B %d, %Y')
    if start > end:
        raise ValueError('Invalid statement range.')
    parsed = [classify(row) for row in rows]
    if len({r['id'] for r in parsed}) != len(parsed):
        raise ValueError('Duplicate transaction identities.')
    if any(not start.date() <= datetime.strptime(r['date'], '%Y-%m-%d').date() <= end.date() for r in parsed):
        raise ValueError('Transaction falls outside the selected date range.')
    snapshot = {'account_key': account, 'source_url': payload['source_url'], 'start_date': start.date().isoformat(),
                'end_date': end.date().isoformat(), 'observed_at': datetime.utcnow().isoformat(), 'rows': parsed,
                'status': 'needs_review' if any(r['category'] == 'unsupported' for r in parsed) else 'captured'}
    digest = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    evidence_key = 'ebay_payment_evidence:' + digest
    if db.scalar(select(AppSetting).where(AppSetting.key == evidence_key)) is None:
        db.add(AppSetting(key=evidence_key,value=json.dumps(payload)))
    snapshot['evidence_ref'] = evidence_key
    key = PREFIX + account
    record = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if record is None:
        record = AppSetting(key=key,value='{}')
        db.add(record)
    record.value = json.dumps(snapshot)
    db.commit()
    return {'status': snapshot['status'], 'transactions': len(parsed), 'evidence_ref': evidence_key}


def report(db, profit_rows, orders, entries):
    snapshots = [json.loads(r.value) for r in db.scalars(select(AppSetting).where(AppSetting.key.startswith(PREFIX))).all()]
    result = []
    order_accounts = {o.ebay_order_id:o.account_id for o in orders}
    for snapshot in snapshots:
        rows = snapshot['rows']
        account = snapshot['account_key']
        tracked = {r['ebay_order_id']: r for r in profit_rows if order_accounts.get(r['ebay_order_id']) == account}
        refunds = sum(r['effect'] for r in rows if r['category'] == 'refund' and r['order_id'] in tracked)
        account_effect = sum(r['effect'] for r in rows if r['category'] in {'payout_fee','fee_credit'})
        untracked = {}
        for row in rows:
            if row['category'] in {'sale','refund'} and row['order_id'] not in tracked:
                untracked[row['order_id']] = round(untracked.get(row['order_id'],0) + row['effect'],2)
        issues = []
        if snapshot.get('error'):
            issues.append(snapshot['error'])
        if snapshot['status'] != 'captured':
            issues.append('Unsupported transaction types require review.')
        if any(e.entry_type in {'refund','fee'} for e in entries):
            issues.append('Existing manual refund/fee records require matching to avoid duplicate deductions.')
        for key, row in tracked.items():
            sales = [s for s in rows if s['category'] == 'sale' and s['order_id'] == key]
            if len(sales) != 1 or row['contribution'] is None or row['revenue'] is None or row['ebay_fees'] is None or abs(sales[0]['net'] - row['revenue'] + row['ebay_fees']) > .001:
                issues.append(f'Sale {key} is missing or differs from order profit evidence.')
        subtotal = sum(r['contribution'] or 0 for r in tracked.values())
        result.append({**snapshot, 'tracked_refund_effect':round(refunds,2), 'account_fee_effect':round(account_effect,2),
            'tracked_contribution_after_adjustments':round(subtotal+refunds+account_effect,2) if tracked and not issues else None,
            'untracked_order_settlements':untracked, 'issues':issues,
            'limitation':'Rolling 90-day eBay records only. Other-order supplier costs, external overhead and expenses remain separate; this is not verified business net profit.'})
    return result


def record_failure(db, account, error):
    if not db.scalar(select(EbayAccount).where(EbayAccount.key == account)):
        raise ValueError('Unknown seller account.')
    key = PREFIX + account
    record = db.scalar(select(AppSetting).where(AppSetting.key == key))
    snapshot = json.loads(record.value) if record else {'account_key':account, 'rows':[], 'start_date':'Unknown', 'end_date':'Unknown', 'observed_at':'Not captured'}
    snapshot.update(status='needs_review', error=str(error)[:500])
    if record is None:
        record = AppSetting(key=key,value='{}')
        db.add(record)
    record.value=json.dumps(snapshot)
    db.commit()

import sqlite3,json,collections,datetime
from pathlib import Path
c=sqlite3.connect('file:C:/AutoZS/data/autozs.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
raw=json.loads(Path('tmp/verified-ready-batch-2026-09-07.json').read_text(encoding='utf-8-sig'))
products=raw['value']['products']; ids=[p['id'] for p in products]
report=[]
for p in products:
 pid=p['id']; jobs=[dict(r) for r in c.execute('select * from listing_jobs where product_id=? order by id desc',(pid,))]; listings=[dict(r) for r in c.execute('select * from ebay_listings where product_id=?',(pid,))]; refresh=[dict(r) for r in c.execute('select * from source_refresh_jobs where product_id=? and batch_key=? order by id desc',(pid,'refresh-20260907164535-a44ddd'))]
 report.append(dict(product_id=pid,title=p['title'],jobs=jobs,listings=listings,refresh=refresh))
Path('tmp/resumed-batch-audit.json').write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),products=report),indent=2))
print('count',len(ids),'ids',ids)
print('refresh',dict(collections.Counter(r['refresh'][0]['status'] if r['refresh'] else 'none' for r in report)))
print('listing latest',dict(collections.Counter(r['jobs'][0]['status'] if r['jobs'] else 'none' for r in report)))
for r in report:
 print(json.dumps(dict(id=r['product_id'],jobs=[{k:j[k] for k in ['id','status','updated_at','message']} for j in r['jobs'][:1]],listings=[{k:l[k] for k in ['listing_id','status']} for l in r['listings']])))

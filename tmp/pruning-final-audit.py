import sqlite3,json
c=sqlite3.connect('file:C:/AutoZS/data/autozs.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
for name,sql in {'pruning':"select status,count(*) n from ebay_revision_jobs where action='end_zero_view' group by status",'running':"select id,product_id,status,listing_schedule_at,message from listing_jobs where status='running'",'legacy_remaining':"select listing_id,views,views_measured_at from ebay_listings where status='active' and removal_reason='zero_views_29_days'"}.items():print(name,json.dumps([dict(r) for r in c.execute(sql)]))

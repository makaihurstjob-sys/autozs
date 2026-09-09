import sqlite3,json
c=sqlite3.connect('file:C:/AutoZS/data/autozs.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
print(json.dumps([dict(r) for r in c.execute("select listing_id,views,views_measured_at,renews_at from ebay_listings where status='active' and removal_reason='zero_views_29_days' and (views != 0 or views_measured_at < datetime('now','-2 hours'))")]))

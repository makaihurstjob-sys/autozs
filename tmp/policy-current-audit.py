import sqlite3,json
c=sqlite3.connect('file:C:/AutoZS/data/autozs.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
for name,sql in {'batches':'select id,status,rows_total,rows_succeeded,rows_failed,result_filename,message from ebay_revision_batches order by id desc limit 4','ended':"select l.listing_id,j.message from ebay_revision_jobs j join ebay_listings l on l.id=j.ebay_listing_id where j.action='end_zero_view' order by j.id desc limit 2"}.items():
 print(name,json.dumps([dict(r) for r in c.execute(sql)]))

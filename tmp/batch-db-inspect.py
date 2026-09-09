import sqlite3,json
c=sqlite3.connect('file:C:/AutoZS/data/autozs.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
for label,sql in [('refresh',"select status,count(*) n from source_refresh_jobs group by status"),('running',"select id,product_id,batch_key,status,message from source_refresh_jobs where status='running'"),('batches',"select batch_key,count(*) n,min(id) first from source_refresh_jobs where status='queued' group by batch_key order by first limit 8")]:
 print(label,json.dumps([dict(r) for r in c.execute(sql)]))

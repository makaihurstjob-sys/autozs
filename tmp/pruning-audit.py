import sqlite3,json
c=sqlite3.connect('file:C:/AutoZS/data/autozs.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
queries={
'listing_counts':'select status,count(*) n from ebay_listings group by status',
'active_quantity_counts':"select case when quantity>0 then 'sellable' else 'zero_quantity' end availability,count(distinct listing_id) n from ebay_listings where status='active' group by availability",
'settings':"select key,value from app_settings where key in ('zero_view_rotation_pending_json','active_listing_cap','active_listing_target_enabled','auto_delist_zero_view_enabled','auto_delist_zero_view_days')",
'revision_counts':'select action,status,count(*) n from ebay_revision_jobs group by action,status',
'recent_retirements':"select id,ebay_listing_id,product_id,action,status,message,updated_at from ebay_revision_jobs where action like '%retir%' order by id desc limit 4",
'retired_state':"select l.status,l.quantity,l.relist_blocked,count(*) n from ebay_listings l where l.id in (select ebay_listing_id from ebay_revision_jobs where action='retire_zero_view' and status='completed') group by l.status,l.quantity,l.relist_blocked",
'queued_jobs':"select id,product_id,status,listing_schedule_at,message from listing_jobs where status in ('queued','running') order by id",
}
for name,sql in queries.items():
 try:print(name,json.dumps([dict(r) for r in c.execute(sql)]))
 except Exception as e:print(name,str(e))

import sqlite3,json
c=sqlite3.connect('file:C:/AutoZS/data/autozs.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
queries={'orders':"select id,ebay_order_id,status,total,ship_by,created_at,shipping_state, shipping_postal_code != '' has_address from orders where account_id != 'sandbox' order by id desc limit 5",'items':"select order_id,product_id,title,quantity,sale_price from order_items where order_id in (select id from orders where account_id != 'sandbox' order by id desc limit 3)",'supplier_orders':"select id,order_id,status,total,approved_total,external_order_id,failure_reason,attempts from supplier_orders order by id desc limit 6"}
for k,q in queries.items():print(k,json.dumps([dict(r) for r in c.execute(q)]))

import sqlite3,json
c=sqlite3.connect('file:C:/AutoZS/data/autozs.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
print(json.dumps([dict(r) for r in c.execute('select supplier,source_url,last_price,last_shipping,in_stock,minimum_order_quantity from supplier_products where product_id=112')]))

import sqlite3,json
from pathlib import Path
c=sqlite3.connect('file:C:/AutoZS/data/autozs.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
a=json.loads(Path('tmp/resumed-batch-audit.json').read_text())
for p in a['products']:
 if not p['jobs']:
  rows=[dict(r) for r in c.execute('select product_id,in_stock,price_unavailable,last_price,last_shipping from supplier_products where product_id=?',(p['product_id'],))]
  print(json.dumps({'id':p['product_id'],'supplier':rows}))

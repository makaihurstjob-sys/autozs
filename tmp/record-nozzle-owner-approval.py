import sqlite3
c=sqlite3.connect('C:/AutoZS/data/autozs.db')
r=c.execute("update supplier_orders set approved_total=5.28, approved_at=datetime('now'), failure_reason=? where id=4 and order_id=4 and status='needs_review' and (external_order_id='' or external_order_id is null) and abs(total-5.28)<0.001",('Owner approved $5.28 in chat after configured card ending 0048 was verified; one submission authorized, inspect confirmation before any retry.',))
if r.rowcount!=1: c.rollback();raise RuntimeError('Order state changed; submission held')
c.commit();print('Recorded owner approval: supplier order 4, $5.28; automatic retries remain held.')

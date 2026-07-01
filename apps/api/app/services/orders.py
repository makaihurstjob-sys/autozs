from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.domain import FulfillmentTask, Order, OrderItem, Product, ProductStatus


def seed_mock_order(db: Session) -> Order:
    existing = db.query(Order).filter(Order.ebay_order_id == "SANDBOX-ORDER-001").first()
    if existing:
        existing.account_id = existing.account_id or "sandbox"
        product = _first_active_product(db)
        for item in existing.items:
            if item.product_id is None and product is not None:
                item.product_id = product.id
                item.title = product.title
        db.commit()
        db.refresh(existing)
        return existing
    order = Order(
        ebay_order_id="SANDBOX-ORDER-001",
        account_id="sandbox",
        buyer_username="sandbox-buyer",
        status="imported",
        ship_by=datetime.utcnow() + timedelta(days=2),
        total=79.99,
    )
    db.add(order)
    db.flush()
    product = _first_active_product(db)
    db.add(
        OrderItem(
            order_id=order.id,
            product_id=product.id if product else None,
            title=product.title if product else "Sandbox order item",
            quantity=1,
            sale_price=79.99,
        )
    )
    db.add(FulfillmentTask(order_id=order.id, status="open", note="Review supplier availability before fulfillment"))
    db.commit()
    db.refresh(order)
    return order


def _first_active_product(db: Session) -> Product | None:
    return (
        db.query(Product)
        .filter(Product.status != ProductStatus.deleted.value)
        .order_by(Product.created_at.asc())
        .first()
    )

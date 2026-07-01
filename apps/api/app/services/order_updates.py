from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.domain import CustomerUpdate, CustomerUpdateStatus, FulfillmentTask, Order


def list_customer_updates(db: Session, status: str | None = None) -> list[CustomerUpdate]:
    stmt = select(CustomerUpdate).order_by(CustomerUpdate.created_at.desc(), CustomerUpdate.id.desc())
    if status:
        stmt = stmt.where(CustomerUpdate.status == status)
    return list(db.scalars(stmt).all())


def generate_order_update_drafts(db: Session, order_id: int | None = None) -> list[CustomerUpdate]:
    stmt = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.fulfillment_tasks), selectinload(Order.customer_updates))
        .order_by(Order.created_at.asc(), Order.id.asc())
    )
    if order_id is not None:
        stmt = stmt.where(Order.id == order_id)
    orders = db.scalars(stmt).all()
    updates: list[CustomerUpdate] = []
    for order in orders:
        event = _event_for_order(order)
        if event is None or _has_update(order, event):
            continue
        subject, body = _message_for_event(order, event)
        update = CustomerUpdate(
            order_id=order.id,
            event=event,
            channel="ebay_message",
            status=CustomerUpdateStatus.draft.value,
            subject=subject,
            body=body,
        )
        db.add(update)
        updates.append(update)
    db.commit()
    for update in updates:
        db.refresh(update)
    return updates


def update_customer_update_status(
    db: Session,
    update_id: int,
    status: str | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> CustomerUpdate | None:
    update = db.get(CustomerUpdate, update_id)
    if update is None:
        return None
    if status is not None:
        update.status = status
        update.sent_at = datetime.utcnow() if status == CustomerUpdateStatus.sent.value else None
    if subject is not None:
        update.subject = subject[:256]
    if body is not None:
        update.body = body
    db.commit()
    db.refresh(update)
    return update


def _event_for_order(order: Order) -> str | None:
    task = _primary_task(order)
    if task is None:
        return "order_received"
    if task.status == "blocked":
        return "fulfillment_blocked"
    if task.status == "in_progress":
        return "fulfillment_started"
    if task.status == "completed":
        return "order_completed"
    if order.status in {"imported", "paid", "awaiting_shipment"}:
        return "order_received"
    return None


def _primary_task(order: Order) -> FulfillmentTask | None:
    return order.fulfillment_tasks[0] if order.fulfillment_tasks else None


def _has_update(order: Order, event: str) -> bool:
    return any(update.event == event and update.status != CustomerUpdateStatus.skipped.value for update in order.customer_updates)


def _message_for_event(order: Order, event: str) -> tuple[str, str]:
    item_summary = _item_summary(order)
    buyer = order.buyer_username or "there"
    if event == "fulfillment_started":
        return (
            f"Update on order {order.ebay_order_id}",
            (
                f"Hi {buyer}, thanks again for your order. We are processing {item_summary} now and will add tracking "
                "as soon as it is available."
            ),
        )
    if event == "fulfillment_blocked":
        task = _primary_task(order)
        reason = task.exception_reason if task and task.exception_reason else "a supplier availability check"
        return (
            f"Order {order.ebay_order_id} update",
            (
                f"Hi {buyer}, we are checking on {item_summary}. The order needs an extra review because of {reason}. "
                "We will follow up as soon as we have the next confirmed update."
            ),
        )
    if event == "order_completed":
        return (
            f"Order {order.ebay_order_id} completed",
            (
                f"Hi {buyer}, {item_summary} has been marked complete on our side. Thank you for your order, "
                "and please message us if anything needs attention."
            ),
        )
    return (
        f"Thanks for order {order.ebay_order_id}",
        (
            f"Hi {buyer}, thanks for your order. We received {item_summary} and are getting it ready for fulfillment."
        ),
    )


def _item_summary(order: Order) -> str:
    if not order.items:
        return "your item"
    total_quantity = sum(item.quantity for item in order.items)
    first = order.items[0].title
    if len(order.items) == 1 and total_quantity == 1:
        return first
    return f"{total_quantity} item(s), including {first}"

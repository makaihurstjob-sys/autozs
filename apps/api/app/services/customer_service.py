from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.domain import CustomerConversation, CustomerMessage, Order
from app.services.customer_templates import render_customer_template


def recipient_first_name(order: Order | None) -> str:
    if order is None:
        return ""
    name = " ".join(str(order.recipient_name or "").strip().split())
    if not name:
        return ""
    parts = name.split()
    while len(parts) > 1 and parts[0].rstrip(".").lower() in {"mr", "mrs", "ms", "miss", "dr"}:
        parts.pop(0)
    return parts[0].strip(" ,.")


def list_conversations(db: Session) -> list[CustomerConversation]:
    return list(
        db.scalars(
            select(CustomerConversation)
            .options(
                selectinload(CustomerConversation.messages),
                selectinload(CustomerConversation.order),
            )
            .order_by(CustomerConversation.last_message_at.desc(), CustomerConversation.updated_at.desc())
        ).unique().all()
    )


def import_conversation(
    db: Session,
    *,
    account_id: str,
    ebay_thread_id: str,
    ebay_order_id: str | None,
    buyer_username: str,
    subject: str,
    messages: list[dict],
) -> CustomerConversation:
    conversation = db.scalar(
        select(CustomerConversation).where(
            CustomerConversation.account_id == account_id,
            CustomerConversation.ebay_thread_id == ebay_thread_id,
        )
    )
    order = db.scalar(select(Order).where(Order.ebay_order_id == ebay_order_id)) if ebay_order_id else None
    if conversation is None:
        conversation = CustomerConversation(account_id=account_id, ebay_thread_id=ebay_thread_id)
        db.add(conversation)
        db.flush()
    conversation.order_id = order.id if order else conversation.order_id
    conversation.buyer_username = buyer_username or conversation.buyer_username
    conversation.subject = subject or conversation.subject
    for payload in messages:
        external_id = payload["external_message_id"]
        existing = db.scalar(
            select(CustomerMessage).where(
                CustomerMessage.conversation_id == conversation.id,
                CustomerMessage.external_message_id == external_id,
            )
        )
        if existing is not None:
            continue
        sent_at = payload.get("sent_at") or datetime.utcnow()
        db.add(
            CustomerMessage(
                conversation_id=conversation.id,
                external_message_id=external_id,
                direction=payload.get("direction", "inbound"),
                origin=payload.get("origin", "buyer"),
                status="sent" if payload.get("direction") == "outbound" else "imported",
                subject=payload.get("subject", ""),
                body=payload["body"],
                sent_at=sent_at,
            )
        )
        if conversation.last_message_at is None or sent_at > conversation.last_message_at:
            conversation.last_message_at = sent_at
    db.commit()
    return _load_conversation(db, conversation.id)


def queue_message(
    db: Session,
    conversation_id: int,
    *,
    body: str,
    subject: str = "",
    origin: str = "human",
    queue_immediately: bool = True,
) -> CustomerMessage:
    conversation = db.get(CustomerConversation, conversation_id)
    if conversation is None:
        raise LookupError("Customer conversation not found.")
    message = CustomerMessage(
        conversation_id=conversation.id,
        direction="outbound",
        origin=origin,
        status="queued" if queue_immediately else "draft",
        subject=subject or conversation.subject,
        body=body.strip(),
    )
    db.add(message)
    conversation.last_message_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    return message


def queue_template_message(
    db: Session,
    conversation_id: int,
    *,
    template_key: str,
    variables: dict[str, str] | None = None,
    subject: str = "",
    origin: str = "human",
    queue_immediately: bool = True,
) -> CustomerMessage:
    conversation = db.get(CustomerConversation, conversation_id)
    if conversation is None:
        raise LookupError("Customer conversation not found.")
    order = db.get(Order, conversation.order_id) if conversation.order_id else None
    merged_variables = {
        "buyer_first_name": recipient_first_name(order),
        **(variables or {}),
    }
    rendered = render_customer_template(template_key, merged_variables)
    unresolved = rendered["unresolved_placeholders"]
    if unresolved:
        raise ValueError("Fill required template fields: " + ", ".join(unresolved))
    if origin == "automatic" and rendered["automation"] != "automatic":
        raise ValueError("This template requires human review and cannot be queued as an automatic message.")
    return queue_message(
        db,
        conversation_id,
        body=rendered["rendered_body"],
        subject=subject,
        origin=origin,
        queue_immediately=queue_immediately,
    )


def ensure_order_thank_you_draft(db: Session, order: Order) -> CustomerMessage | None:
    thread_id = f"order:{order.ebay_order_id}"
    conversation = db.scalar(
        select(CustomerConversation).where(
            CustomerConversation.account_id == order.account_id,
            CustomerConversation.ebay_thread_id == thread_id,
        )
    )
    if conversation is None:
        conversation = CustomerConversation(
            account_id=order.account_id,
            ebay_thread_id=thread_id,
            order_id=order.id,
            buyer_username=order.buyer_username or "",
            subject=f"Thanks for order {order.ebay_order_id}",
            last_message_at=datetime.utcnow(),
        )
        db.add(conversation)
        db.flush()
    existing = db.scalar(
        select(CustomerMessage).where(
            CustomerMessage.conversation_id == conversation.id,
            CustomerMessage.origin == "automatic",
            CustomerMessage.subject == f"Thanks for order {order.ebay_order_id}",
        )
    )
    if existing is not None:
        return None
    rendered = render_customer_template(
        "post_sale_thank_you",
        {
            "buyer_first_name": recipient_first_name(order) or "there",
            "seller_first_name": "Makail",
        },
    )
    message = CustomerMessage(
        conversation_id=conversation.id,
        direction="outbound",
        origin="automatic",
        status="queued",
        subject=f"Thanks for order {order.ebay_order_id}",
        body=rendered["rendered_body"],
    )
    db.add(message)
    return message


def queue_missing_order_thank_yous(db: Session) -> list[CustomerMessage]:
    orders = list(
        db.scalars(
            select(Order)
            .options(selectinload(Order.items))
            .order_by(Order.created_at.asc(), Order.id.asc())
        ).all()
    )
    queued: list[CustomerMessage] = []
    for order in orders:
        message = ensure_order_thank_you_draft(db, order)
        if message is not None:
            queued.append(message)
    db.commit()
    for message in queued:
        db.refresh(message)
    return queued


def claim_next_outbound_message(db: Session) -> CustomerMessage | None:
    now = datetime.utcnow()
    stale = db.scalars(
        select(CustomerMessage).where(
            CustomerMessage.status == "sending",
            CustomerMessage.lease_expires_at.is_not(None),
            CustomerMessage.lease_expires_at < now,
        )
    ).all()
    for message in stale:
        message.status = "queued"
        message.error = "Chrome send lease expired; safely returned to queue."
        message.lease_expires_at = None
    message = db.scalar(
        select(CustomerMessage)
        .where(CustomerMessage.direction == "outbound", CustomerMessage.status == "queued")
        .order_by(CustomerMessage.created_at.asc(), CustomerMessage.id.asc())
    )
    if message is None:
        db.commit()
        return None
    message.status = "sending"
    message.attempts = int(message.attempts or 0) + 1
    message.lease_expires_at = now + timedelta(minutes=5)
    db.commit()
    db.refresh(message)
    return message


def update_message(db: Session, message: CustomerMessage, values: dict) -> CustomerMessage:
    for field in ("external_message_id", "sent_at", "error"):
        if field in values:
            setattr(message, field, values[field])
    if values.get("status"):
        message.status = values["status"]
        if message.status == "sent":
            message.sent_at = message.sent_at or datetime.utcnow()
            message.lease_expires_at = None
        elif message.status in {"failed", "cancelled"}:
            message.lease_expires_at = None
    db.commit()
    db.refresh(message)
    return message


def _load_conversation(db: Session, conversation_id: int) -> CustomerConversation:
    return db.scalar(
        select(CustomerConversation)
        .options(selectinload(CustomerConversation.messages))
        .where(CustomerConversation.id == conversation_id)
    )

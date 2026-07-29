from datetime import datetime, timedelta
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.domain import (
    FulfillmentTask,
    GiftCard,
    GiftCardLedgerEntry,
    Order,
    Product,
    SupplierOrder,
    SupplierOrderItem,
    SupplierOrderStatus,
)


ACTIVE_SUPPLIER_ORDER_STATUSES = {
    SupplierOrderStatus.draft.value,
    SupplierOrderStatus.needs_review.value,
    SupplierOrderStatus.queued.value,
    SupplierOrderStatus.placing.value,
    SupplierOrderStatus.placed.value,
    SupplierOrderStatus.shipped.value,
}


def list_gift_cards(db: Session) -> list[GiftCard]:
    return list(db.scalars(select(GiftCard).order_by(GiftCard.status, GiftCard.created_at.desc())).all())


def create_gift_card(
    db: Session,
    *,
    supplier: str,
    label: str,
    last_four: str,
    face_value: float,
    acquisition_cost: float,
    current_balance: float | None,
    secret_ref: str,
    notes: str | None,
) -> GiftCard:
    balance = float(face_value if current_balance is None else current_balance)
    if balance > float(face_value):
        raise ValueError("Gift-card balance cannot exceed its face value.")
    card = GiftCard(
        supplier=supplier.strip().lower(),
        label=label.strip(),
        last_four="".join(character for character in last_four if character.isdigit())[-4:],
        face_value=round(float(face_value), 2),
        acquisition_cost=round(float(acquisition_cost), 2),
        current_balance=round(balance, 2),
        status="active" if balance > 0 else "depleted",
        secret_ref=secret_ref.strip(),
        notes=notes,
    )
    db.add(card)
    db.flush()
    db.add(GiftCardLedgerEntry(
        gift_card_id=card.id,
        event="acquired",
        amount=round(balance, 2),
        balance_after=round(balance, 2),
        note=f"Acquired for ${float(acquisition_cost):,.2f}.",
    ))
    db.commit()
    db.refresh(card)
    return card


def update_gift_card(
    db: Session,
    card: GiftCard,
    *,
    label: str | None = None,
    current_balance: float | None = None,
    status: str | None = None,
    secret_ref: str | None = None,
    notes: str | None = None,
) -> GiftCard:
    if label is not None:
        card.label = label.strip()
    if current_balance is not None:
        balance = round(float(current_balance), 2)
        if balance > float(card.face_value):
            raise ValueError("Gift-card balance cannot exceed its face value.")
        delta = round(balance - float(card.current_balance or 0), 2)
        card.current_balance = balance
        if delta:
            db.add(GiftCardLedgerEntry(
                gift_card_id=card.id,
                event="adjustment",
                amount=delta,
                balance_after=balance,
                note="Manual balance reconciliation.",
            ))
        if status is None:
            card.status = "active" if balance > 0 else "depleted"
    if status is not None:
        card.status = status
    if secret_ref is not None:
        card.secret_ref = secret_ref.strip()
    if notes is not None:
        card.notes = notes
    db.commit()
    db.refresh(card)
    return card


def list_supplier_orders(db: Session, order_id: int | None = None) -> list[SupplierOrder]:
    stmt = (
        select(SupplierOrder)
        .options(selectinload(SupplierOrder.items), selectinload(SupplierOrder.gift_card))
        .order_by(SupplierOrder.created_at.desc(), SupplierOrder.id.desc())
    )
    if order_id is not None:
        stmt = stmt.where(SupplierOrder.order_id == order_id)
    return list(db.scalars(stmt).unique().all())


def prepare_supplier_order(
    db: Session,
    order_id: int,
    *,
    gift_card_id: int | None = None,
    recipient_name: str = "",
    address_line1: str = "",
    address_line2: str = "",
    city: str = "",
    state: str = "",
    postal_code: str = "",
    phone: str = "",
) -> SupplierOrder:
    order = db.scalar(
        select(Order)
        .options(
            selectinload(Order.items),
            selectinload(Order.supplier_orders).selectinload(SupplierOrder.items),
        )
        .where(Order.id == order_id)
    )
    if order is None:
        raise LookupError("Order not found.")
    existing = next(
        (supplier_order for supplier_order in order.supplier_orders if supplier_order.status in ACTIVE_SUPPLIER_ORDER_STATUSES),
        None,
    )
    if existing is not None:
        if gift_card_id is not None:
            card = db.get(GiftCard, gift_card_id)
            if card is None:
                raise ValueError("Selected gift card was not found.")
            existing.gift_card_id = card.id
            existing.supplier = card.supplier
        _apply_recipient(
            existing,
            recipient_name=recipient_name,
            address_line1=address_line1,
            address_line2=address_line2,
            city=city,
            state=state,
            postal_code=postal_code,
            phone=phone,
        )
        _refresh_supplier_order_readiness(db, existing)
        db.commit()
        return _load_supplier_order(db, existing.id)

    card = db.get(GiftCard, gift_card_id) if gift_card_id is not None else None
    if gift_card_id is not None and card is None:
        raise ValueError("Selected gift card was not found.")
    supplier_order = SupplierOrder(
        order_id=order.id,
        gift_card_id=card.id if card else None,
        supplier=card.supplier if card else "home_depot",
        payment_method="gift_card" if card else "credit_card",
    )
    _apply_recipient(
        supplier_order,
        recipient_name=recipient_name,
        address_line1=address_line1,
        address_line2=address_line2,
        city=city,
        state=state,
        postal_code=postal_code,
        phone=phone,
    )
    db.add(supplier_order)
    db.flush()

    suppliers_seen: set[str] = set()
    shipping_total = 0.0
    for item in order.items:
        product = db.get(Product, item.product_id) if item.product_id else None
        supplier_product = product.supplier_products[0] if product and product.supplier_products else None
        supplier = (supplier_product.supplier if supplier_product else "unknown").strip().lower()
        suppliers_seen.add(supplier)
        quantity = max(
            int(item.quantity or 1),
            int(supplier_product.minimum_order_quantity or 1) if supplier_product else 1,
        )
        unit_price = float(supplier_product.last_price or 0) if supplier_product else 0.0
        source_url = supplier_product.source_url if supplier_product else ""
        shipping_total += float(supplier_product.last_shipping or 0) if supplier_product else 0.0
        db.add(SupplierOrderItem(
            supplier_order_id=supplier_order.id,
            order_item_id=item.id,
            product_id=item.product_id,
            title=item.title,
            quantity=quantity,
            unit_price=round(unit_price, 2),
            source_url=source_url,
        ))
    db.flush()
    supplier_order = _load_supplier_order(db, supplier_order.id)
    if supplier_order is None:
        raise RuntimeError("Supplier order could not be reloaded after preparation.")
    if len(suppliers_seen) == 1 and "unknown" not in suppliers_seen:
        supplier_order.supplier = next(iter(suppliers_seen))
    elif len(suppliers_seen) > 1:
        supplier_order.failure_reason = "This eBay order contains products from multiple suppliers and must be split."
    supplier_order.shipping_cost = round(shipping_total, 2)
    _refresh_supplier_order_readiness(db, supplier_order)
    db.commit()
    return _load_supplier_order(db, supplier_order.id)


def approve_supplier_order(db: Session, supplier_order_id: int) -> SupplierOrder:
    supplier_order = _load_supplier_order(db, supplier_order_id)
    if supplier_order is None:
        raise LookupError("Supplier order not found.")
    missing = _readiness_issues(supplier_order)
    if missing:
        supplier_order.status = SupplierOrderStatus.needs_review.value
        supplier_order.failure_reason = "Missing: " + ", ".join(missing)
        db.commit()
        raise ValueError(supplier_order.failure_reason)
    supplier_order.status = SupplierOrderStatus.queued.value
    supplier_order.approved_total = round(float(supplier_order.total or 0), 2)
    supplier_order.approved_at = datetime.utcnow()
    supplier_order.checkout_token = ""
    supplier_order.failure_reason = None
    db.commit()
    return _load_supplier_order(db, supplier_order.id)


def claim_next_supplier_order(db: Session) -> SupplierOrder | None:
    now = datetime.utcnow()
    stale = db.scalars(
        select(SupplierOrder).where(
            SupplierOrder.status == SupplierOrderStatus.placing.value,
            SupplierOrder.lease_expires_at.is_not(None),
            SupplierOrder.lease_expires_at < now,
        )
    ).all()
    for supplier_order in stale:
        supplier_order.status = SupplierOrderStatus.queued.value
        supplier_order.failure_reason = "Browser checkout lease expired; safely returned to the queue."
        supplier_order.lease_expires_at = None
        supplier_order.checkout_token = ""
    active = db.scalar(
        select(SupplierOrder.id).where(
            SupplierOrder.status == SupplierOrderStatus.placing.value,
            SupplierOrder.lease_expires_at.is_not(None),
            SupplierOrder.lease_expires_at >= now,
        )
    )
    if active is not None:
        db.commit()
        return None
    supplier_order = db.scalar(
        select(SupplierOrder)
        .options(selectinload(SupplierOrder.items), selectinload(SupplierOrder.gift_card))
        .where(SupplierOrder.status == SupplierOrderStatus.queued.value)
        .order_by(SupplierOrder.approved_at.asc(), SupplierOrder.id.asc())
    )
    if supplier_order is None:
        db.commit()
        return None
    supplier_order.status = SupplierOrderStatus.placing.value
    supplier_order.attempts = int(supplier_order.attempts or 0) + 1
    supplier_order.lease_expires_at = now + timedelta(minutes=10)
    supplier_order.checkout_token = secrets.token_urlsafe(32)
    db.commit()
    return _load_supplier_order(db, supplier_order.id)


def update_supplier_order(
    db: Session,
    supplier_order: SupplierOrder,
    values: dict[str, Any],
) -> SupplierOrder:
    allowed = {
        "external_order_id",
        "item_subtotal",
        "sales_tax",
        "shipping_cost",
        "gift_card_amount",
        "card_amount",
        "total",
        "tracking_number",
        "carrier",
        "estimated_delivery",
        "failure_reason",
        "recipient_name",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "phone",
    }
    for key in allowed:
        if key in values and values[key] is not None:
            setattr(supplier_order, key, values[key])
    status = values.get("status")
    if status is not None:
        if status == SupplierOrderStatus.placed.value:
            reported_total = round(float(values.get("total", supplier_order.total) or 0), 2)
            approved_total = round(float(supplier_order.approved_total or 0), 2)
            if not supplier_order.external_order_id and not values.get("external_order_id"):
                raise ValueError("Supplier order confirmation number is required before marking an order placed.")
            if approved_total <= 0 or abs(reported_total - approved_total) > 0.01:
                raise ValueError(
                    f"Checkout total ${reported_total:,.2f} does not match the approved total ${approved_total:,.2f}."
                )
        _apply_supplier_order_status(db, supplier_order, status)
    elif supplier_order.status in {SupplierOrderStatus.draft.value, SupplierOrderStatus.needs_review.value}:
        _refresh_supplier_order_readiness(db, supplier_order)
    db.commit()
    return _load_supplier_order(db, supplier_order.id)


def _apply_recipient(supplier_order: SupplierOrder, **values: str) -> None:
    for key, value in values.items():
        if value:
            setattr(supplier_order, key, value.strip())


def _refresh_supplier_order_readiness(db: Session, supplier_order: SupplierOrder) -> None:
    supplier_order.item_subtotal = round(
        sum(float(item.unit_price or 0) * int(item.quantity or 1) for item in supplier_order.items),
        2,
    )
    supplier_order.total = round(
        float(supplier_order.item_subtotal or 0)
        + float(supplier_order.sales_tax or 0)
        + float(supplier_order.shipping_cost or 0),
        2,
    )
    card = db.get(GiftCard, supplier_order.gift_card_id) if supplier_order.gift_card_id else None
    if card is not None:
        supplier_order.payment_method = "gift_card"
        supplier_order.gift_card_amount = round(min(float(card.current_balance or 0), supplier_order.total), 2)
    else:
        supplier_order.payment_method = "credit_card"
        supplier_order.gift_card_amount = 0.0
    supplier_order.card_amount = round(max(0.0, supplier_order.total - supplier_order.gift_card_amount), 2)
    supplier_order.source_url = next((item.source_url for item in supplier_order.items if item.source_url), "")
    issues = _readiness_issues(supplier_order)
    supplier_order.status = SupplierOrderStatus.needs_review.value if issues else SupplierOrderStatus.draft.value
    supplier_order.failure_reason = "Missing: " + ", ".join(issues) if issues else None


def _readiness_issues(supplier_order: SupplierOrder) -> list[str]:
    issues: list[str] = []
    if not supplier_order.items:
        issues.append("supplier items")
    elif any(not item.source_url or float(item.unit_price or 0) <= 0 for item in supplier_order.items):
        issues.append("current supplier price/source")
    if supplier_order.supplier not in {"home_depot", "lowes"}:
        issues.append("supported supplier")
    for label, value in (
        ("recipient name", supplier_order.recipient_name),
        ("shipping address", supplier_order.address_line1),
        ("city", supplier_order.city),
        ("state", supplier_order.state),
        ("postal code", supplier_order.postal_code),
    ):
        if not str(value or "").strip():
            issues.append(label)
    if float(supplier_order.total or 0) <= 0:
        issues.append("purchase total")
    ebay_revenue = round(float(supplier_order.order.total or 0), 2) if supplier_order.order is not None else 0.0
    supplier_total = round(float(supplier_order.total or 0), 2)
    if ebay_revenue > 0 and supplier_total > ebay_revenue:
        issues.append(
            f"supplier total ${supplier_total:,.2f} exceeds eBay order revenue ${ebay_revenue:,.2f}"
        )
    if supplier_order.gift_card_id:
        card = supplier_order.gift_card
        if card is None or card.status != "active":
            issues.append("active gift card")
        elif not card.secret_ref:
            issues.append("gift-card credential reference")
    return issues


def _apply_supplier_order_status(db: Session, supplier_order: SupplierOrder, status: str) -> None:
    now = datetime.utcnow()
    if status == SupplierOrderStatus.placed.value:
        _debit_gift_card_once(db, supplier_order)
        supplier_order.placed_at = supplier_order.placed_at or now
        supplier_order.lease_expires_at = None
        _update_fulfillment_task(
            db,
            supplier_order.order_id,
            "in_progress",
            f"{supplier_order.supplier.replace('_', ' ').title()} order {supplier_order.external_order_id or 'placed'} is processing.",
        )
    elif status == SupplierOrderStatus.shipped.value:
        supplier_order.shipped_at = supplier_order.shipped_at or now
        supplier_order.lease_expires_at = None
        tracking = f" Tracking: {supplier_order.tracking_number}." if supplier_order.tracking_number else ""
        _update_fulfillment_task(db, supplier_order.order_id, "in_progress", f"Supplier order shipped.{tracking}")
    elif status == SupplierOrderStatus.delivered.value:
        supplier_order.delivered_at = supplier_order.delivered_at or now
        supplier_order.lease_expires_at = None
        _update_fulfillment_task(db, supplier_order.order_id, "completed", "Supplier reports the order delivered.")
    elif status == SupplierOrderStatus.failed.value:
        supplier_order.lease_expires_at = None
        _update_fulfillment_task(
            db,
            supplier_order.order_id,
            "blocked",
            "Supplier checkout needs review.",
            supplier_order.failure_reason or "Supplier checkout failed.",
        )
    elif status == SupplierOrderStatus.cancelled.value:
        supplier_order.lease_expires_at = None
    if status != SupplierOrderStatus.placing.value:
        supplier_order.checkout_token = ""
    supplier_order.status = status


def _debit_gift_card_once(db: Session, supplier_order: SupplierOrder) -> None:
    amount = round(float(supplier_order.gift_card_amount or 0), 2)
    if not supplier_order.gift_card_id or amount <= 0:
        return
    existing = db.scalar(
        select(GiftCardLedgerEntry).where(
            GiftCardLedgerEntry.gift_card_id == supplier_order.gift_card_id,
            GiftCardLedgerEntry.supplier_order_id == supplier_order.id,
            GiftCardLedgerEntry.event == "purchase",
        )
    )
    if existing is not None:
        return
    card = db.get(GiftCard, supplier_order.gift_card_id)
    if card is None or float(card.current_balance or 0) + 0.001 < amount:
        raise ValueError("Gift-card balance is no longer sufficient for this supplier order.")
    card.current_balance = round(float(card.current_balance) - amount, 2)
    card.status = "active" if card.current_balance > 0 else "depleted"
    db.add(GiftCardLedgerEntry(
        gift_card_id=card.id,
        supplier_order_id=supplier_order.id,
        event="purchase",
        amount=-amount,
        balance_after=card.current_balance,
        note=f"Applied to supplier order for eBay order {supplier_order.order.ebay_order_id}.",
    ))


def _update_fulfillment_task(
    db: Session,
    order_id: int,
    status: str,
    note: str,
    exception_reason: str | None = None,
) -> None:
    task = db.scalar(select(FulfillmentTask).where(FulfillmentTask.order_id == order_id).order_by(FulfillmentTask.id))
    if task is None:
        task = FulfillmentTask(order_id=order_id)
        db.add(task)
    task.status = status
    task.note = note
    task.exception_reason = exception_reason


def _load_supplier_order(db: Session, supplier_order_id: int) -> SupplierOrder | None:
    return db.scalar(
        select(SupplierOrder)
        .options(
            selectinload(SupplierOrder.items),
            selectinload(SupplierOrder.gift_card),
            selectinload(SupplierOrder.order),
        )
        .where(SupplierOrder.id == supplier_order_id)
    )

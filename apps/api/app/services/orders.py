import csv
from datetime import datetime, timedelta
from io import BytesIO, StringIO, TextIOWrapper
import re
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import (
    EbayListing,
    EbaySyncRun,
    EbaySyncRunStatus,
    FulfillmentTask,
    ListingJob,
    ListingJobStatus,
    Order,
    OrderItem,
    Product,
    ProductStatus,
)
from app.services.customer_service import ensure_order_thank_you_draft


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


def parse_ebay_order_report(content: bytes, filename: str = "ebay-orders.csv") -> list[dict[str, str]]:
    if filename.lower().endswith(".zip"):
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = [name for name in archive.namelist() if name.lower().endswith((".csv", ".tsv", ".txt"))]
                if not names:
                    raise ValueError("The eBay Orders ZIP did not contain a CSV file.")
                with archive.open(names[0]) as source:
                    text = TextIOWrapper(source, encoding="utf-8-sig", errors="replace").read()
        except BadZipFile as exc:
            raise ValueError("The downloaded eBay Orders ZIP is invalid.") from exc
    else:
        text = content.decode("utf-8-sig", errors="replace")
    if not text.strip():
        raise ValueError("The downloaded eBay Orders report is empty.")
    lines = text.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if "order number" in line.lower() and "item number" in line.lower()
        ),
        None,
    )
    if header_index is None:
        raise ValueError("The eBay Orders report did not contain its Order Number header.")
    text = "\n".join(lines[header_index:])
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",\t")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in text.splitlines()[0] else csv.excel
    rows = [
        {str(key or "").strip(): str(value or "").strip() for key, value in row.items() if key is not None}
        for row in csv.DictReader(StringIO(text), dialect=dialect)
    ]
    rows = [row for row in rows if any(row.values())]
    if not rows:
        raise ValueError("The eBay Orders report did not contain any order rows.")
    return rows


def import_ebay_order_report_rows(
    db: Session,
    *,
    rows: list[dict[str, str]],
    account_key: str,
    run_id: int | None = None,
    filename: str | None = None,
) -> tuple[int, int, int]:
    normalized = [_normalize_order_row(row) for row in rows]
    normalized = [row for row in normalized if row["order_id"] and (row["item_number"] or row["title"])]
    if not normalized:
        raise ValueError("No Order Number values were found in the eBay Orders report.")

    grouped: dict[str, list[dict]] = {}
    for row in normalized:
        grouped.setdefault(row["order_id"], []).append(row)

    upserted = 0
    unmatched = 0
    new_orders: list[Order] = []
    for ebay_order_id, order_rows in grouped.items():
        order = db.scalar(select(Order).where(Order.ebay_order_id == ebay_order_id))
        is_new = order is None
        if order is None:
            order = Order(ebay_order_id=ebay_order_id, account_id=account_key)
            db.add(order)
            db.flush()
        order.account_id = account_key
        reported_sales_record_number = next(
            (row["sales_record_number"] for row in order_rows if row["sales_record_number"]),
            "",
        )
        if reported_sales_record_number:
            order.sales_record_number = reported_sales_record_number
        order.buyer_username = next((row["buyer_username"] for row in order_rows if row["buyer_username"]), None)
        reported_recipient_name = next(
            (row["recipient_name"] for row in order_rows if row["recipient_name"]),
            "",
        )
        if reported_recipient_name:
            order.recipient_name = reported_recipient_name
        for field in (
            "shipping_address_line1",
            "shipping_address_line2",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country",
        ):
            reported = next((row[field] for row in order_rows if row[field]), "")
            if reported:
                setattr(order, field, reported)
        order.ship_by = _minimum_date(row["ship_by"] for row in order_rows)
        order.status = _order_status(order_rows)
        reported_totals = [row["total"] for row in order_rows if row["total"] is not None]
        order.total = max(reported_totals) if reported_totals else round(
            sum((row["sold_for"] or 0.0) * row["quantity"] + (row["shipping"] or 0.0) for row in order_rows),
            2,
        )

        db.query(OrderItem).filter(OrderItem.order_id == order.id).delete(synchronize_session=False)
        for row in order_rows:
            product = _match_order_product(db, account_key=account_key, row=row)
            if product is None:
                unmatched += 1
            elif is_new and order.status != "cancelled":
                _queue_automatic_restock(
                    db,
                    product=product,
                    account_key=account_key,
                    item_number=row["item_number"],
                    quantity=row["quantity"],
                )
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id if product else None,
                    title=row["title"] or (product.title if product else f"eBay item {row['item_number'] or 'unknown'}"),
                    quantity=row["quantity"],
                    sale_price=row["sold_for"] or 0.0,
                    expected_profit=_expected_order_item_profit(product, row),
                )
            )

        if is_new:
            new_orders.append(order)
            task_status = "completed" if order.status == "shipped" else "blocked" if order.status == "cancelled" else "open"
            note = (
                "eBay reports this order as shipped."
                if task_status == "completed"
                else "Do not fulfill: eBay reports this order as cancelled."
                if task_status == "blocked"
                else "New eBay sale detected. Review supplier availability and place the supplier order."
            )
            db.add(
                FulfillmentTask(
                    order_id=order.id,
                    status=task_status,
                    note=note,
                    exception_reason="Cancelled on eBay" if task_status == "blocked" else None,
                )
            )
        elif order.status == "shipped" and order.fulfillment_tasks:
            order.fulfillment_tasks[0].status = "completed"
            order.fulfillment_tasks[0].note = "eBay reports this order as shipped."
        upserted += 1

    db.flush()
    for order in new_orders:
        db.expire(order, ["items"])
        ensure_order_thank_you_draft(db, order)

    run = db.get(EbaySyncRun, run_id) if run_id else None
    if run is not None:
        run.status = EbaySyncRunStatus.completed.value
        run.phase = "completed"
        run.completed_at = datetime.utcnow()
        run.report_filename = filename or run.report_filename
        run.orders_seen = len(grouped)
        run.orders_upserted = upserted
        run.message = (
            f"Imported {upserted} eBay order{'s' if upserted != 1 else ''}. "
            f"{unmatched} line item{'s' if unmatched != 1 else ''} could not be matched to an AutoZS product."
        )
    db.commit()
    return len(grouped), upserted, unmatched


def _queue_automatic_restock(
    db: Session,
    *,
    product: Product,
    account_key: str,
    item_number: str,
    quantity: int,
) -> None:
    listing = None
    if item_number:
        listing = db.scalar(
            select(EbayListing).where(
                EbayListing.account_id == account_key,
                EbayListing.listing_id == item_number,
                EbayListing.product_id == product.id,
            )
        )
    if listing is None:
        listing = db.scalar(
            select(EbayListing)
            .where(
                EbayListing.account_id == account_key,
                EbayListing.product_id == product.id,
                EbayListing.status.in_(("scheduled", "listed", "live", "active")),
            )
            .order_by(EbayListing.created_at.desc(), EbayListing.id.desc())
        )
    if listing is None:
        return

    listing.quantity = max(0, int(listing.quantity or 0) - max(1, int(quantity or 1)))
    if listing.quantity > 0:
        return
    listing.status = "ended"

    _queue_replacement_publish(db, product=product, account_key=account_key, excluded_listing_id=listing.id)


def reconcile_sold_listing_replacements(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Repair the sale-to-relist handoff until a replacement is confirmed active.

    Order import starts this workflow, but imports are intentionally idempotent and
    therefore cannot repair a job that later fails. This reconciler uses the durable
    sale, ended listing, and current active-listing evidence on every worker pass.
    """
    checked_at = now or datetime.utcnow()
    sold_product_ids = set(
        db.scalars(
            select(OrderItem.product_id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(OrderItem.product_id.is_not(None), Order.status != "cancelled")
        ).all()
    )
    result = {"candidates": 0, "queued": 0, "awaiting_confirmation": 0, "confirmed_active": 0}
    for product_id in sold_product_ids:
        product = db.get(Product, product_id)
        if product is None or product.status == ProductStatus.deleted.value:
            continue
        sold_out_listing = db.scalar(
            select(EbayListing)
            .where(
                EbayListing.product_id == product_id,
                # Seller Hub continues to call out-of-stock fixed-price items
                # active. The durable sale plus quantity zero is the signal;
                # requiring status=ended strands them after the next report sync.
                EbayListing.status.in_(("ended", "active", "live", "listed")),
                EbayListing.quantity <= 0,
                EbayListing.relist_blocked.is_(False),
            )
            .order_by(EbayListing.updated_at.desc(), EbayListing.id.desc())
        )
        if sold_out_listing is None:
            continue
        result["candidates"] += 1
        account_key = sold_out_listing.account_id
        live_replacement = db.scalar(
            select(EbayListing.id).where(
                EbayListing.product_id == product_id,
                EbayListing.account_id == account_key,
                EbayListing.status.in_(("active", "live", "listed")),
                EbayListing.quantity > 0,
            )
        )
        if live_replacement is not None:
            result["confirmed_active"] += 1
            continue
        pending_listing = db.scalar(
            select(EbayListing.id).where(
                EbayListing.product_id == product_id,
                EbayListing.account_id == account_key,
                EbayListing.status == "scheduled",
                EbayListing.quantity > 0,
            )
        )
        open_job = _open_replacement_job(db, product_id=product_id, account_key=account_key)
        if pending_listing is not None or open_job is not None:
            result["awaiting_confirmation"] += 1
            continue
        if _queue_replacement_publish(
            db,
            product=product,
            account_key=account_key,
            now=checked_at,
            require_confirmed_stock=True,
            excluded_listing_id=sold_out_listing.id,
        ):
            result["queued"] += 1
    db.commit()
    return result


def _open_replacement_job(db: Session, *, product_id: int, account_key: str) -> ListingJob | None:
    return db.scalar(
        select(ListingJob)
        .where(
            ListingJob.product_id == product_id,
            ListingJob.ebay_account_key == account_key,
            ListingJob.action == "publish",
            ListingJob.status.in_(
                (
                    ListingJobStatus.queued.value,
                    ListingJobStatus.running.value,
                    ListingJobStatus.needs_review.value,
                    ListingJobStatus.ready_to_save.value,
                    ListingJobStatus.paused.value,
                )
            ),
        )
        .order_by(ListingJob.created_at.desc(), ListingJob.id.desc())
    )


def _queue_replacement_publish(
    db: Session,
    *,
    product: Product,
    account_key: str,
    now: datetime | None = None,
    require_confirmed_stock: bool = False,
    excluded_listing_id: int | None = None,
) -> bool:
    checked_at = now or datetime.utcnow()
    supplier = product.supplier_products[0] if product.supplier_products else None
    if (
        supplier is None
        or supplier.in_stock is False
        or (require_confirmed_stock and supplier.in_stock is not True)
        or (require_confirmed_stock and supplier.price_unavailable is True)
        or supplier.last_price is None
        or supplier.last_shipping is None
        or float(supplier.last_shipping) < 0
        or (require_confirmed_stock and supplier.updated_at < checked_at - timedelta(hours=24))
    ):
        return False
    another_sellable_listing = db.scalar(
        select(EbayListing).where(
            EbayListing.id != excluded_listing_id if excluded_listing_id is not None else EbayListing.id.is_not(None),
            EbayListing.account_id == account_key,
            EbayListing.product_id == product.id,
            EbayListing.status.in_(("scheduled", "listed", "live", "active")),
            EbayListing.quantity > 0,
        )
    )
    if another_sellable_listing is not None:
        return False
    if _open_replacement_job(db, product_id=product.id, account_key=account_key) is not None:
        return False

    listing_schedule_at = (now or datetime.utcnow()) + timedelta(minutes=30)
    product.listing_schedule_at = listing_schedule_at
    db.add(
        ListingJob(
            product_id=product.id,
            ebay_account_key=account_key,
            action="publish",
            scheduled_for=None,
            listing_schedule_at=listing_schedule_at,
            status=ListingJobStatus.queued.value,
            message="Queued automatic restock after a new eBay sale.",
        )
    )
    return True


def _normalize_order_row(raw: dict[str, str]) -> dict:
    values = {_header_key(key): str(value or "").strip() for key, value in raw.items()}

    def pick(*aliases: str) -> str:
        return next((values.get(_header_key(alias), "") for alias in aliases if values.get(_header_key(alias), "")), "")

    return {
        "order_id": pick("Order Number", "Order ID", "Sales Record Number"),
        "sales_record_number": pick("Sales Record Number", "Sales Record #"),
        "buyer_username": pick("Buyer Username", "User Id"),
        "recipient_name": pick(
            "Ship To Name",
            "Shipping Name",
            "Recipient Name",
            "Buyer Name",
            "Full Name",
        ),
        "shipping_address_line1": pick(
            "Ship To Address 1", "Shipping Address 1", "Ship To Street 1", "Address Line 1"
        ),
        "shipping_address_line2": pick(
            "Ship To Address 2", "Shipping Address 2", "Ship To Street 2", "Address Line 2"
        ),
        "shipping_city": pick("Ship To City", "Shipping City", "City"),
        "shipping_state": pick("Ship To State", "Shipping State", "State"),
        "shipping_postal_code": pick(
            "Ship To Zip", "Ship To Postal Code", "Shipping Postal Code", "Zip Code", "Postal Code"
        ),
        "shipping_country": pick("Ship To Country", "Shipping Country", "Country") or "United States",
        "item_number": re.sub(r"\D", "", pick("Item Number", "Item ID", "eBay Item Number")),
        "custom_label": pick("Custom Label", "SKU"),
        "title": pick("Item Title", "Title"),
        "quantity": max(1, int(_number(pick("Quantity", "Quantity Sold")) or 1)),
        "sold_for": _money(pick("Sold For", "Sale Price", "Item Price")),
        "shipping": _money(pick("Shipping And Handling", "Shipping and Handling", "Shipping")),
        "total": _money(pick("Total Price", "Order Total", "Total")),
        "paid_on": _date(pick("Paid On Date", "Paid on Date")),
        "ship_by": _date(pick("Ship By Date", "Ship by date")),
        "shipped_on": _date(pick("Shipped On Date", "Shipped on Date")),
        "tracking_number": pick("Tracking Number"),
        "raw_status": pick("Order Status", "Status", "Cancel Status"),
    }


def _match_order_product(db: Session, *, account_key: str, row: dict) -> Product | None:
    if row["item_number"]:
        listing = db.scalar(
            select(EbayListing).where(
                EbayListing.account_id == account_key,
                EbayListing.listing_id == row["item_number"],
            )
        )
        if listing:
            return db.get(Product, listing.product_id)
    if row["custom_label"]:
        product = db.scalar(select(Product).where(Product.sku == row["custom_label"]))
        if product:
            return product
    title_key = _title_key(row["title"])
    if not title_key:
        return None
    matches = [
        product
        for product in db.scalars(select(Product).where(Product.status != ProductStatus.deleted.value)).all()
        if _title_key(product.title) == title_key
    ]
    return matches[0] if len(matches) == 1 else None


def _expected_order_item_profit(product: Product | None, row: dict) -> float | None:
    if product is None or not product.supplier_products or row["sold_for"] is None:
        return None
    supplier = product.supplier_products[0]
    if supplier.last_price is None:
        return None
    quantity = max(1, int(row["quantity"] or 1))
    source_units = max(quantity, int(supplier.minimum_order_quantity or 1))
    source_cost = float(supplier.last_price) * source_units + float(supplier.last_shipping or 0.0)
    revenue = float(row["sold_for"]) * quantity
    variable_rate = float(product.ebay_fee_rate or 0.0) + float(product.promoted_rate or 0.0) + float(product.return_risk_rate or 0.0)
    return round(revenue - source_cost - revenue * variable_rate - float(product.fixed_costs or 0.0), 2)


def _order_status(rows: list[dict]) -> str:
    status_text = " ".join(str(row["raw_status"] or "") for row in rows).lower()
    if "cancel" in status_text:
        return "cancelled"
    if any(row["shipped_on"] or row["tracking_number"] for row in rows):
        return "shipped"
    if any(row["paid_on"] for row in rows):
        return "imported"
    return "awaiting_payment"


def _minimum_date(values) -> datetime | None:
    dates = [value for value in values if value is not None]
    return min(dates) if dates else None


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _title_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _number(value: str) -> float | None:
    match = re.search(r"-?[\d,]+(?:\.\d+)?", str(value or ""))
    return float(match.group(0).replace(",", "")) if match else None


def _money(value: str) -> float | None:
    parsed = _number(value)
    if parsed is None:
        return None
    return -abs(parsed) if str(value or "").strip().startswith("(") else parsed


def _date(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        pass
    without_zone = re.sub(r"\s+(?:PST|PDT|MST|MDT|CST|CDT|EST|EDT|GMT|UTC)$", "", text, flags=re.IGNORECASE)
    for fmt in (
        "%b %d, %Y %I:%M:%S %p",
        "%b %d, %Y %I:%M %p",
        "%b-%d-%y",
        "%b-%d-%y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(without_zone, fmt)
        except ValueError:
            continue
    return None

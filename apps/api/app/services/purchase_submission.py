"""Final supplier submission gate; disabled until explicitly configured."""
from datetime import datetime, timezone
from decimal import Decimal
import hmac
import json
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import AppSetting, SupplierOrder
from app.services import purchase_budget
from app.services.ebay_checkout_verification import require_fresh
from app.services.purchase_policy import cents, evaluate_purchase
from app.services.profit_reconciliation import state_for


class CheckoutItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_url: str
    quantity: int = Field(strict=True, gt=0)
    unit_price: Decimal


class FinalCheckout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_subtotal: Decimal
    shipping: Decimal
    tax: Decimal
    total: Decimal
    source_url: str
    observed_at: datetime
    items: list[CheckoutItem]
    saved_payment: Literal["privacy"]


def authorize_submission(db: Session, supplier_order_id: int, token: str, quote: FinalCheckout, *, dry_run: bool = False):
    # Serialize the entire check/reserve/consume operation, including the first
    # request. A repeated request must never reproduce permission to click.
    purchase_budget._lock(db)
    enabled = db.scalar(select(AppSetting.value).where(AppSetting.key == "purchase_automation_enabled"))
    if enabled != "true":
        raise ValueError("Automatic purchasing is disabled")
    row = db.get(SupplierOrder, supplier_order_id, populate_existing=True)
    now = datetime.now(timezone.utc)
    if (row is None or row.status != "placing" or not token or not row.checkout_token
            or not hmac.compare_digest(token, row.checkout_token)
            or row.lease_expires_at is None
            or row.lease_expires_at.replace(tzinfo=timezone.utc) <= now):
        raise ValueError("A current checkout lease is required")
    if row.supplier != "home_depot" or len(row.items) != 1 or row.gift_card_id:
        raise ValueError("Automatic submission supports one Home Depot item paid by card")
    from app.services.fulfillment import require_owner_place_order
    require_owner_place_order(db, row)
    from app.services.purchase_approval import require_approval, audit
    approval = require_approval(db, row)
    require_fresh(db, row)
    url = urlsplit(quote.source_url)
    if url.scheme != "https" or url.netloc != "www.homedepot.com" or url.path.rstrip("/") != "/checkout":
        raise ValueError("Final totals must come from Home Depot checkout")
    if quote.observed_at.tzinfo is None or not 0 <= (now - quote.observed_at).total_seconds() <= 30:
        raise ValueError("Final checkout totals are stale")
    order = row.order
    if order.account_id == "sandbox" or state_for(db, order.id).get("status") != "verified":
        raise ValueError("Verified marketplace financial evidence is required")
    if not order.ebay_fee_evidence_ref or order.ebay_fee_recorded_at is None:
        raise ValueError("Actual marketplace fee evidence is required")
    if not order.items or any(type(i.quantity) is not int or i.quantity <= 0 for i in order.items):
        raise ValueError("Order item revenue is incomplete")
    proceeds = sum(cents(i.sale_price, "Item revenue") * i.quantity for i in order.items)
    proceeds += cents(order.buyer_shipping_revenue, "Buyer shipping revenue")
    other = db.scalar(select(AppSetting.value).where(AppSetting.key == f"purchase_other_costs:{order.id}"))
    try:
        other = json.loads(other or "null")
        if not isinstance(other, dict) or not str(other.get("evidence", "")).strip():
            raise ValueError()
        other_cost = other["amount"]
    except (ValueError, KeyError, TypeError):
        raise ValueError("Verified other costs, including explicit zero, are required") from None
    evaluation = evaluate_purchase(item_subtotal=quote.item_subtotal, shipping=quote.shipping,
        tax=quote.tax, checkout_total=quote.total, seller_proceeds=Decimal(proceeds) / 100,
        marketplace_fees=order.ebay_fee_amount, other_costs=other_cost)
    expected = sum(cents(i.unit_price, "Supplier item") * i.quantity for i in row.items)
    if cents(quote.item_subtotal, "Subtotal") != expected:
        raise ValueError("Final item subtotal differs from the supplier draft")
    if evaluation.supplier_total_cents > cents(row.approved_total, "Approved total"):
        raise ValueError("Final total exceeds the approved ceiling")
    approved_items = approval["items"]
    if len(quote.items) != len(approved_items) or any(
        actual.source_url != expected["source_url"] or actual.quantity != expected["quantity"]
        or cents(actual.unit_price, "Checkout unit price") != expected["unit_price_cents"]
        for actual, expected in zip(quote.items, approved_items)
    ):
        raise ValueError("Final item or quantity changed; new approval is required")
    for actual, field in ((quote.item_subtotal, "item_subtotal_cents"), (quote.shipping, "shipping_cents"),
                          (quote.tax, "tax_cents"), (quote.total, "total_cents")):
        if cents(actual, field) != approval[field]:
            raise ValueError("Final price changed; new approval is required")
    if dry_run:
        # No reservation, consumption, approval or click permission in preview mode.
        return {"authorized": False, "dry_run": True, "supplier_order_id": row.id,
                "total_cents": evaluation.supplier_total_cents}
    reservation = purchase_budget.reserve(db, order_id=order.id, supplier_order_id=row.id,
        evaluation=evaluation, now=now, checkout_token=token)
    purchase_budget.begin_submission(db, row.id)
    audit(db, row.id, "submission_requested", approval_id=approval["approval_id"], reservation_id=reservation.id)
    row.item_subtotal, row.shipping_cost, row.sales_tax = map(float, (quote.item_subtotal, quote.shipping, quote.tax))
    row.total = row.approved_total = row.card_amount = float(quote.total)
    result = {"authorized": True, "supplier_order_id": row.id, "reservation_id": reservation.id,
              "total_cents": evaluation.supplier_total_cents}
    db.commit()  # durable before permission leaves this process
    return result


def stage_changed_quote(db: Session, supplier_order_id: int, token: str, quote: FinalCheckout):
    """Replace a pre-submit plan for owner review; never returns purchase permission."""
    purchase_budget._lock(db)
    row = db.get(SupplierOrder, supplier_order_id, populate_existing=True)
    now = datetime.now(timezone.utc)
    if (row is None or row.status != "placing" or not token or not row.checkout_token
            or not hmac.compare_digest(token, row.checkout_token) or row.lease_expires_at is None
            or row.lease_expires_at.replace(tzinfo=timezone.utc) <= now):
        raise ValueError("A current checkout lease is required")
    purchase_budget.require_unreserved(db, row.order_id)
    from app.services.purchase_approval import require_approval, audit
    require_approval(db, row)
    require_fresh(db, row)
    url = urlsplit(quote.source_url)
    if url.scheme != "https" or url.netloc != "www.homedepot.com" or url.path.rstrip("/") != "/checkout":
        raise ValueError("Final totals must come from Home Depot checkout")
    if quote.observed_at.tzinfo is None or not 0 <= (now - quote.observed_at).total_seconds() <= 30:
        raise ValueError("Final checkout totals are stale")
    expected_items = sorted(row.items, key=lambda item: item.id)
    if len(quote.items) != len(expected_items) or any(
        actual.source_url != expected.source_url or actual.quantity != expected.quantity
        for actual, expected in zip(quote.items, expected_items)
    ):
        raise ValueError("Different checkout items or quantities need reconciliation before a new plan")
    subtotal, shipping, tax, total = (cents(v, label) for v, label in (
        (quote.item_subtotal, "Subtotal"), (quote.shipping, "Shipping"), (quote.tax, "Tax"), (quote.total, "Total")))
    item_total = sum(cents(item.unit_price, "Unit price") * item.quantity for item in quote.items)
    if total <= 0 or subtotal <= 0 or subtotal != item_total or total != subtotal + shipping + tax:
        raise ValueError("Checkout quote must include consistent item, shipping, tax and total costs")
    for actual, expected in zip(quote.items, expected_items):
        expected.unit_price = float(actual.unit_price)
    row.item_subtotal, row.shipping_cost, row.sales_tax, row.total = map(float,
        (quote.item_subtotal, quote.shipping, quote.tax, quote.total))
    row.card_amount = row.total
    row.approved_at = None
    row.approved_total = 0
    row.checkout_token = ""
    row.lease_expires_at = None
    # Keep all readiness guards, without replacing actual quoted tax with an estimate.
    from app.services.fulfillment import _readiness_issues, _finish_purchase_attempt
    issues = _readiness_issues(row)
    row.status = "needs_review" if issues else "draft"
    row.failure_reason = "Checkout price changed; review the updated plan and approve again."
    if issues:
        row.failure_reason += " Missing: " + ", ".join(issues)
    _finish_purchase_attempt(db, row, "awaiting_approval")
    audit(db, row.id, "held", status="price_changed_new_approval_required")
    db.commit()
    return {"authorized": False, "new_approval_required": True, "supplier_order_id": row.id}

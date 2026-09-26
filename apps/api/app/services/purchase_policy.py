"""Fail-closed monetary checks for automated supplier purchases.

Callers must supply verified full checkout costs and marketplace net proceeds.
This module does not authorize submission or infer missing fees as zero.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def cents(value: object, name: str) -> int:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} is missing or invalid")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} is missing or invalid") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    scaled = amount * 100
    if scaled != scaled.to_integral_value():
        raise ValueError(f"{name} must be expressed in whole cents")
    return int(scaled)


@dataclass(frozen=True)
class BuyingLimits:
    per_order_cents: int = 50_000
    daily_cents: int = 10_000
    minimum_profit_cents: int = 25

    def __post_init__(self):
        for value in (self.per_order_cents, self.daily_cents, self.minimum_profit_cents):
            if type(value) is not int or value < 0:
                raise ValueError("Limits must be nonnegative integer cents")
        if not self.per_order_cents or not self.daily_cents:
            raise ValueError("Spending limits must be positive")


@dataclass(frozen=True)
class PurchaseEvaluation:
    supplier_total_cents: int
    net_profit_cents: int


def evaluate_purchase(*, item_subtotal: object, shipping: object, tax: object,
                      checkout_total: object, seller_proceeds: object,
                      marketplace_fees: object, other_costs: object,
                      limits: BuyingLimits = BuyingLimits()) -> PurchaseEvaluation:
    """seller_proceeds excludes buyer tax; fees must include all marketplace fees.

    Explicit zero is valid; None means unknown and blocks buying. Daily budget
    must separately be reserved atomically before any submission permission.
    """
    subtotal = cents(item_subtotal, "Item subtotal")
    delivery = cents(shipping, "Shipping")
    sales_tax = cents(tax, "Supplier tax")
    total = cents(checkout_total, "Checkout total")
    proceeds = cents(seller_proceeds, "Seller proceeds")
    fees = cents(marketplace_fees, "Marketplace fees")
    other = cents(other_costs, "Other costs")
    if total <= 0 or total != subtotal + delivery + sales_tax:
        raise ValueError("Checkout total must be positive and match all supplier costs")
    if total > limits.per_order_cents:
        raise ValueError("Per-order spending limit exceeded")
    if total > limits.daily_cents:
        raise ValueError("Daily spending limit exceeded")
    profit = proceeds - fees - other - total
    if profit < limits.minimum_profit_cents:
        raise ValueError("Minimum net profit not met")
    return PurchaseEvaluation(total, profit)

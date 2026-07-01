from dataclasses import dataclass

from app.models.domain import Product, SupplierProduct


@dataclass(frozen=True)
class RepricingDecision:
    floor_price: float | None
    suggested_price: float | None
    message: str


def calculate_floor_price(
    supplier_cost: float,
    supplier_shipping: float,
    fixed_costs: float,
    desired_profit: float,
    risk_buffer: float,
    ebay_fee_rate: float,
    promoted_rate: float,
    return_risk_rate: float,
) -> float:
    fee_factor = 1 - ebay_fee_rate - promoted_rate - return_risk_rate
    if fee_factor <= 0:
        raise ValueError("Fee rates must leave a positive selling-price factor")
    floor_price = (
        supplier_cost + supplier_shipping + fixed_costs + desired_profit + risk_buffer
    ) / fee_factor
    return round(floor_price, 2)


def decide_reprice(
    product: Product,
    supplier_product: SupplierProduct | None,
    gift_card_discount_percent: float = 0.0,
) -> RepricingDecision:
    if supplier_product is None:
        return RepricingDecision(None, None, "No supplier product attached")
    if not supplier_product.in_stock:
        return RepricingDecision(None, None, "Supplier product is out of stock")
    if supplier_product.last_price is None:
        return RepricingDecision(None, None, "Supplier price has not been captured yet")

    discount = max(0.0, min(gift_card_discount_percent, 100.0))
    effective_supplier_cost = round(supplier_product.last_price * (1 - discount / 100), 2)
    floor_price = calculate_floor_price(
        supplier_cost=effective_supplier_cost,
        supplier_shipping=max(supplier_product.last_shipping, 0.0),
        fixed_costs=product.fixed_costs,
        desired_profit=product.desired_profit,
        risk_buffer=product.risk_buffer,
        ebay_fee_rate=product.ebay_fee_rate,
        promoted_rate=product.promoted_rate,
        return_risk_rate=product.return_risk_rate,
    )

    if product.competitor_price is None:
        return RepricingDecision(floor_price, floor_price, "No competitor price; using floor price")

    target_price = round(product.competitor_price - product.undercut_amount, 2)
    suggested_price = max(floor_price, target_price)
    if suggested_price > target_price:
        message = "Competitor price is below profitable floor"
    else:
        message = "Undercut competitor while preserving floor"
    return RepricingDecision(floor_price, suggested_price, message)

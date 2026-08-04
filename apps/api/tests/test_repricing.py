import pytest

from app.services.importer import calculate_listing_price, calculate_profit, effective_supplier_cost
from app.services.repricing import calculate_floor_price


def test_calculate_floor_price() -> None:
    price = calculate_floor_price(
        supplier_cost=50.0,
        supplier_shipping=0.0,
        fixed_costs=0.0,
        desired_profit=8.0,
        risk_buffer=3.0,
        ebay_fee_rate=0.1325,
        promoted_rate=0.0,
        return_risk_rate=0.02,
    )
    assert price == 71.98


def test_calculate_floor_price_rejects_bad_fee_factor() -> None:
    with pytest.raises(ValueError):
        calculate_floor_price(10, 0, 0, 1, 1, 0.8, 0.2, 0.1)


def test_gift_card_discount_reduces_cost_and_increases_profit() -> None:
    settings = {
        "default_gift_card_discount_enabled": True,
        "default_gift_card_discount_percent": 6.0,
        "default_ebay_fee_rate": 0.10,
        "default_promoted_rate": 0.0,
        "default_return_risk_rate": 0.0,
    }

    assert effective_supplier_cost(99.0, settings) == 93.06
    assert calculate_profit(120.0, 99.0, 0.0, settings)["profit"] == 14.94


def test_minimum_order_quantity_multiplies_supplier_cost() -> None:
    settings = {
        "default_gift_card_discount_enabled": False,
        "default_ebay_fee_rate": 0.10,
        "default_promoted_rate": 0.0,
        "default_return_risk_rate": 0.0,
    }

    assert calculate_profit(40.0, 14.19, 0.0, settings, minimum_order_quantity=2)["profit"] == 7.62


def test_minimum_profit_guard_clamps_competitor_strategy() -> None:
    settings = {
        "default_margin_percent": 0.20,
        "default_undercut_amount": 0.20,
        "default_min_profit": 2.0,
        "default_min_profit_guard_enabled": True,
        "default_ebay_fee_rate": 0.10,
        "default_promoted_rate": 0.0,
        "default_return_risk_rate": 0.0,
        "default_pricing_strategy": "competitor",
        "default_round_to_99": False,
    }

    decision = calculate_listing_price(93.06, 100.0, settings)

    assert decision.competitor_target_price == 99.8
    assert decision.minimum_profit_price == 105.62
    assert decision.final_price == 105.62
    assert "minimum-profit guard" in decision.reason


def test_selected_repricing_only_returns_selected_products(client) -> None:
    first = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Selected-Reprice-One/1001",
            "title": "Selected Reprice One",
            "source_price": 10.0,
            "source_shipping": 0.0,
            "description": "First selected repricing product",
            "image_urls": "https://example.com/first.jpg",
        },
    ).json()
    second = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Selected-Reprice-Two/1002",
            "title": "Selected Reprice Two",
            "source_price": 20.0,
            "source_shipping": 0.0,
            "description": "Second selected repricing product",
            "image_urls": "https://example.com/second.jpg",
        },
    ).json()

    response = client.post("/repricing/run-selected", json={"product_ids": [first["id"]]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] == 1
    assert [snapshot["product_id"] for snapshot in payload["snapshots"]] == [first["id"]]
    assert second["id"] != first["id"]


def test_sales_tax_raises_supplier_cost_and_reduces_profit() -> None:
    """Supplier sales tax is real cash out and must reduce projected profit."""
    settings = {
        "default_gift_card_discount_enabled": False,
        "default_sales_tax_percent": 8.25,
        "default_ebay_fee_rate": 0.10,
        "default_promoted_rate": 0.0,
        "default_return_risk_rate": 0.0,
    }

    # 100.00 merchandise + 8.25% tax
    assert effective_supplier_cost(100.0, settings) == 108.25
    # 130 sell - 108.25 cost - 13.00 fees
    assert calculate_profit(130.0, 100.0, 0.0, settings)["profit"] == 8.75


def test_sales_tax_defaults_to_zero_and_changes_nothing() -> None:
    settings = {
        "default_gift_card_discount_enabled": False,
        "default_ebay_fee_rate": 0.10,
        "default_promoted_rate": 0.0,
        "default_return_risk_rate": 0.0,
    }

    assert effective_supplier_cost(100.0, settings) == 100.0


def test_sales_tax_applies_before_the_gift_card_discount() -> None:
    """A gift card pays the taxed total, so the discount is earned on that total."""
    settings = {
        "default_gift_card_discount_enabled": True,
        "default_gift_card_discount_percent": 6.0,
        "default_sales_tax_percent": 10.0,
        "default_ebay_fee_rate": 0.10,
        "default_promoted_rate": 0.0,
        "default_return_risk_rate": 0.0,
    }

    # 100 * 1.10 = 110.00 charged, paid with a card bought at 6% off -> 103.40
    assert effective_supplier_cost(100.0, settings) == 103.40


def test_sales_tax_raises_the_repricing_floor() -> None:
    from app.models.domain import Product, SupplierProduct
    from app.services.repricing import decide_reprice

    product = Product(
        sku="TAX-1",
        title="Taxed product",
        fixed_costs=0.0,
        desired_profit=2.0,
        risk_buffer=0.0,
        ebay_fee_rate=0.10,
        promoted_rate=0.0,
        return_risk_rate=0.0,
        undercut_amount=0.0,
    )
    supplier = SupplierProduct(
        supplier="home_depot", source_url="https://example.com/p/1", last_price=100.0, last_shipping=0.0, in_stock=True
    )

    untaxed = decide_reprice(product, supplier, 0.0, 0.0)
    taxed = decide_reprice(product, supplier, 0.0, 8.25)

    assert untaxed.floor_price == 113.33
    assert taxed.floor_price > untaxed.floor_price
    assert taxed.floor_price == 122.5


BREAKEVEN_SETTINGS = {
    "default_margin_percent": 0.20,
    "default_undercut_amount": 0.20,
    "default_min_profit": 2.0,
    "default_min_profit_guard_enabled": True,
    "default_ebay_fee_rate": 0.10,
    "default_promoted_rate": 0.0,
    "default_return_risk_rate": 0.0,
    "default_gift_card_discount_enabled": False,
    "default_pricing_strategy": "breakeven",
    "default_round_to_99": True,
    "default_rounding_cents": 0.99,
}


def test_breakeven_mode_prices_at_exactly_zero_profit() -> None:
    decision = calculate_listing_price(100.0, None, BREAKEVEN_SETTINGS)

    assert decision.strategy == "breakeven"
    assert decision.final_price == 111.11
    assert calculate_profit(decision.final_price, 100.0, 0.0, BREAKEVEN_SETTINGS)["profit"] == 0.0


def test_breakeven_mode_overrides_margin_guard_and_rounding() -> None:
    """The mode is defined as overriding every other pricing setting."""
    decision = calculate_listing_price(100.0, 500.0, BREAKEVEN_SETTINGS)

    # margin would be 133.33, the minimum-profit floor 113.33, rounding would push
    # to .99, and a competitor undercut would target 499.80. None may apply.
    assert decision.final_price == 111.11
    assert decision.final_price < decision.margin_price
    assert decision.final_price < decision.minimum_profit_price
    assert not str(decision.final_price).endswith("99")


def test_breakeven_mode_undercuts_every_other_strategy() -> None:
    breakeven = calculate_listing_price(100.0, None, BREAKEVEN_SETTINGS).final_price
    for strategy in ("margin", "safe_competitor"):
        other = calculate_listing_price(100.0, None, {**BREAKEVEN_SETTINGS, "default_pricing_strategy": strategy})
        assert breakeven < other.final_price, f"breakeven must undercut {strategy}"


def test_breakeven_mode_still_includes_sales_tax_in_cost() -> None:
    """Breakeven must clear real cash cost, so tax cannot be dropped."""
    from app.services.importer import effective_landed_cost

    settings = {**BREAKEVEN_SETTINGS, "default_sales_tax_percent": 10.0}
    landed = effective_landed_cost(100.0, 0.0, settings)
    decision = calculate_listing_price(landed, None, settings)

    assert landed == 110.0
    assert decision.final_price == 122.22
    assert calculate_profit(decision.final_price, 100.0, 0.0, settings)["profit"] == 0.0

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

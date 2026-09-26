import pytest

from app.services.purchase_policy import BuyingLimits, cents, evaluate_purchase


def quote(**overrides):
    values = dict(item_subtotal="8.00", shipping="1.00", tax="1.00",
                  checkout_total="10.00", seller_proceeds="12.00",
                  marketplace_fees="1.50", other_costs="0.25")
    values.update(overrides)
    return evaluate_purchase(**values)


def test_exact_minimum_profit_is_accepted():
    result = quote()
    assert result.supplier_total_cents == 1000
    assert result.net_profit_cents == 25


def test_one_cent_below_minimum_is_blocked():
    with pytest.raises(ValueError, match="Minimum net profit"):
        quote(other_costs="0.26")


@pytest.mark.parametrize("field", ["item_subtotal", "shipping", "tax", "checkout_total",
                                   "seller_proceeds", "marketplace_fees", "other_costs"])
def test_unknown_cost_or_proceeds_blocks(field):
    with pytest.raises(ValueError):
        quote(**{field: None})


@pytest.mark.parametrize("value", [True, False, "NaN", "Infinity", "-1", "0.0025", "", object()])
def test_invalid_money_blocks(value):
    with pytest.raises(ValueError):
        cents(value, "money")


def test_total_must_include_shipping_and_tax():
    with pytest.raises(ValueError, match="match all supplier costs"):
        quote(checkout_total="8.00")


def test_daily_cap_also_limits_single_purchase():
    with pytest.raises(ValueError, match="Daily spending"):
        quote(item_subtotal="98.01", checkout_total="100.01", seller_proceeds="200")


def test_per_order_cap_applies_independently():
    with pytest.raises(ValueError, match="Per-order"):
        quote(limits=BuyingLimits(per_order_cents=999))


def test_zero_known_fees_valid_and_daily_boundary_inclusive():
    result = quote(item_subtotal="98", checkout_total="100", seller_proceeds="100.25",
                   marketplace_fees=0, other_costs=0)
    assert result.net_profit_cents == 25

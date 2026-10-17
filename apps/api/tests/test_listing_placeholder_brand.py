import pytest

from test_listing_jobs import create_ready_product


@pytest.mark.parametrize("brand", [".N/A", "N/A", "Unknown", "null"])
def test_placeholder_brand_blocks_readiness(client, brand):
    product = create_ready_product(client, title=f"{brand} Garden Hose Repair Kit")
    report = client.get(f"/products/{product['id']}/listing-readiness").json()
    assert report["manual_ready"] is False
    assert report["api_ready"] is False
    assert any("Brand is a placeholder" in reason for reason in report["missing_manual"])


@pytest.mark.parametrize("brand", ["Orbit", "Unbranded"])
def test_factual_or_confirmed_unbranded_value_remains_ready(client, brand):
    product = create_ready_product(client, title=f"{brand} Garden Hose Repair Kit")
    report = client.get(f"/products/{product['id']}/listing-readiness").json()
    assert report["manual_ready"] is True

def test_source_monitoring_cycle_prioritizes_products_that_need_capture(client) -> None:
    missing_shipping = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Missing-Shipping/111",
            "title": "Missing Shipping Product",
            "source_price": 14.0,
            "description": "Needs shipping detection",
            "image_urls": "https://images.thdstatic.com/productImages/missing-shipping.jpg",
        },
    ).json()
    ready = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Ready-Monitoring/222",
            "title": "Ready Monitoring Product",
            "source_price": 20.0,
            "source_shipping": 0.0,
            "description": "Already fresh",
            "image_urls": "https://images.thdstatic.com/productImages/ready-monitoring.jpg",
        },
    ).json()
    client.post(f"/products/{ready['id']}/draft-price", json={"mode": "minimum_profit"})

    queue = client.get("/repricing/source-refresh-queue").json()
    by_id = {item["product_id"]: item for item in queue["items"]}

    assert by_id[missing_shipping["id"]]["priority"] == "high"
    assert by_id[missing_shipping["id"]]["extension_ready"] is True
    assert by_id[ready["id"]]["priority"] == "low"

    run = client.post("/automation/source-monitoring-cycle").json()

    assert run["needs_refresh"] == 1
    assert run["high_priority"] == 1
    assert run["extension_ready"] == 1
    assert "browser capture" in run["message"]
    assert run["run_id"] > 0

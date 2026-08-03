import base64
from datetime import date, timedelta


METRICS = [
    "TOTAL_IMPRESSION_TOTAL",
    "LISTING_IMPRESSION_TOTAL",
    "LISTING_IMPRESSION_SEARCH_RESULTS_PAGE",
    "LISTING_IMPRESSION_STORE",
    "LISTING_VIEWS_TOTAL",
    "LISTING_VIEWS_SOURCE_DIRECT",
    "LISTING_VIEWS_SOURCE_OFF_EBAY",
    "LISTING_VIEWS_SOURCE_OTHER_EBAY",
    "LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE",
    "LISTING_VIEWS_SOURCE_STORE",
    "CLICK_THROUGH_RATE",
    "SALES_CONVERSION_RATE",
    "TRANSACTION",
]


def traffic_report(dimension: str, rows: list[tuple[str, list[float]]]) -> dict:
    today = date.today()
    return {
        "reportType": "TRAFFIC",
        "header": {
            "dimensionKeys": [{"key": dimension, "localizedName": dimension.lower(), "dataType": "STRING"}],
            "metrics": [{"key": key, "localizedName": key, "dataType": "NUMBER"} for key in METRICS],
        },
        "records": [
            {
                "dimensionValues": [{"value": dimension_value, "applicable": True}],
                "metricValues": [{"value": value, "applicable": True} for value in values],
            }
            for dimension_value, values in rows
        ],
        "startDate": f"{today - timedelta(days=6)}T00:00:00Z",
        "endDate": f"{today}T23:59:59Z",
        "lastUpdatedDate": f"{today}T12:00:00Z",
    }


def test_traffic_import_aggregates_all_official_metrics_and_rankings(client) -> None:
    today = date.today()
    day_values = [1000, 900, 800, 100, 100, 10, 5, 20, 55, 10, 0.085, 0.02, 2]
    listing_a = [800, 750, 700, 50, 80, 5, 5, 20, 45, 5, 0.0875, 0.025, 2]
    listing_b = [200, 150, 100, 50, 20, 5, 0, 5, 5, 5, 0.075, 0, 0]

    daily = client.post(
        "/stats/traffic/import",
        json={
            "account_key": "a.m.anim-59",
            "account_id": "a.m.anim-59",
            "marketplace_id": "EBAY_US",
            "dimension": "DAY",
            "report": traffic_report("DAY", [(today.isoformat(), day_values)]),
        },
    )
    assert daily.status_code == 200
    assert daily.json()["records_imported"] == 1

    listings = client.post(
        "/stats/traffic/import",
        json={
            "account_key": "a.m.anim-59",
            "account_id": "a.m.anim-59",
            "marketplace_id": "EBAY_US",
            "dimension": "LISTING",
            "report": traffic_report("LISTING", [("800000000001", listing_a), ("800000000002", listing_b)]),
        },
    )
    assert listings.status_code == 200
    assert listings.json()["records_imported"] == 2

    response = client.get("/stats/traffic?range=30&grain=day&account=a.m.anim-59")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_source"] == "ebay_analytics_api"
    assert payload["summary"]["total_impressions"] == 1000
    assert payload["summary"]["total_views"] == 100
    assert payload["summary"]["transactions"] == 2
    assert payload["summary"]["click_through_rate"] == 0.085
    assert payload["summary"]["sales_conversion_rate"] == 0.02
    assert payload["trend"][0]["label"] == today.isoformat()
    assert payload["best_listings"][0]["listing_id"] == "800000000001"
    assert payload["worst_listings"][0]["listing_id"] == "800000000001"
    metric_keys = {metric["key"] for metric in payload["available_metrics"]}
    assert set(METRICS).issubset(metric_keys)


def test_traffic_import_is_idempotent_for_same_account_dimension_and_period(client) -> None:
    today = date.today()
    original = [100, 90, 80, 10, 10, 1, 1, 2, 5, 1, 0.08, 0.1, 1]
    updated = [200, 180, 160, 20, 20, 2, 2, 4, 10, 2, 0.08, 0.1, 2]
    request = {
        "account_key": "a.m.anim-59",
        "account_id": "a.m.anim-59",
        "marketplace_id": "EBAY_US",
        "dimension": "DAY",
        "report": traffic_report("DAY", [(today.isoformat(), original)]),
    }
    assert client.post("/stats/traffic/import", json=request).status_code == 200
    request["report"] = traffic_report("DAY", [(today.isoformat(), updated)])
    assert client.post("/stats/traffic/import", json=request).status_code == 200

    payload = client.get("/stats/traffic?range=30&grain=day&account=a.m.anim-59").json()
    assert len(payload["trend"]) == 1
    assert payload["summary"]["total_impressions"] == 200
    assert payload["summary"]["total_views"] == 20
    assert payload["summary"]["transactions"] == 2


def test_traffic_falls_back_to_existing_rolling_listing_views(client) -> None:
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/example/100000001",
            "title": "Traffic fallback item",
            "source_price": 10,
            "source_shipping": 0,
            "images": ["https://example.com/image.jpg"],
        },
    ).json()
    marked = client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "800000000099", "account_id": "a.m.anim-59", "status": "active"},
    )
    assert marked.status_code == 200
    capture = client.post(
        "/ebay/sync-runs/listing-views",
        json={
            "account_key": "a.m.anim-59",
            "rows": [{"listing_id": "800000000099", "views": 37}],
        },
    )
    assert capture.status_code == 200

    payload = client.get("/stats/traffic?range=30&grain=day&account=a.m.anim-59").json()
    assert payload["data_source"] == "active_listing_view_scrape"
    assert payload["summary"]["total_views"] == 37
    assert payload["summary"]["listings_measured"] == 1


def test_listing_traffic_import_updates_product_card_view_measurement(client) -> None:
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/example/100000002",
            "title": "Traffic card item",
            "source_price": 12,
            "source_shipping": 0,
            "images": ["https://example.com/image.jpg"],
        },
    ).json()
    marked = client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "800000000100", "account_id": "a.m.anim-59", "status": "active"},
    )
    assert marked.status_code == 200
    listing_values = [500, 500, 0, 0, 42, 0, 2, 0, 0, 0, 0.08, 0, 0]
    imported = client.post(
        "/stats/traffic/import",
        json={
            "account_key": "a.m.anim-59",
            "account_id": "a.m.anim-59",
            "marketplace_id": "EBAY_US",
            "dimension": "LISTING",
            "report": traffic_report("LISTING", [("800000000100", listing_values)]),
        },
    )
    assert imported.status_code == 200

    listing = next(
        item for item in client.get("/ebay/listings").json()
        if item["listing_id"] == "800000000100"
    )
    assert listing["views"] == 42
    assert listing["views_measured_at"] is not None
    assert listing["view_delta"] is None
    history = client.get(f"/ebay/listings/{listing['id']}/view-history").json()
    assert history[0]["views"] == 42


def test_chrome_extension_can_queue_and_import_seller_hub_traffic(client) -> None:
    account = client.post(
        "/ebay/accounts",
        json={"label": "a.m.anim-59", "account_id": "a.m.anim-59", "environment": "production"},
    ).json()
    queued = client.post(f"/stats/traffic/sync?range=30&account={account['key']}")
    assert queued.status_code == 200
    assert queued.json()["queued"] is True
    run_id = queued.json()["run_id"]

    claimed = client.post(f"/ebay/sync-runs/traffic/next?account_key={account['key']}")
    assert claimed.status_code == 200
    assert claimed.json()["id"] == run_id
    assert claimed.json()["status"] == "running"
    assert "/sh/performance/traffic#" in claimed.json()["runner_url"]
    reclaimed = client.post(f"/ebay/sync-runs/traffic/next?account_key={account['key']}")
    assert reclaimed.status_code == 200
    assert reclaimed.json()["id"] == run_id
    assert reclaimed.json()["status"] == "running"

    csv_text = (
        "Item ID,Listing title,Available items,Impressions,eBay views,External views,"
        "Quantity sold,Click-through rate,Sales conversion rate\n"
        "800123456789,Traffic test listing,1,\"1,000\",80,20,2,8.0%,2.0%\n"
    )
    imported = client.post(
        "/stats/traffic/import-file",
        json={
            "account_key": account["key"],
            "run_id": run_id,
            "filename": "active-listings-traffic.csv",
            "report_base64": base64.b64encode(csv_text.encode()).decode(),
        },
    )
    assert imported.status_code == 200
    assert imported.json()["records_imported"] == 1

    overview = client.get(f"/stats/traffic?range=30&grain=day&account={account['key']}").json()
    assert overview["data_source"] == "seller_hub_traffic_report"
    assert overview["summary"]["total_impressions"] == 1000
    assert overview["summary"]["total_views"] == 100
    assert overview["summary"]["transactions"] == 2
    assert overview["summary"]["click_through_rate"] == 0.08
    metric_values = {item["key"]: item["value"] for item in overview["available_metrics"]}
    assert metric_values["SELLER_HUB_AVAILABLE_ITEMS"] == 1

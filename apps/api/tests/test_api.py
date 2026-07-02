import base64
import json

import httpx

from app.services import ebay, importer


def test_research_approval_supplier_and_repricing_flow(client) -> None:
    response = client.post("/research/jobs", json={"source": "keyword", "query": "garage shelf"})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    candidates = client.get("/research/candidates?status=pending").json()
    assert len(candidates) == 3

    product = client.post(f"/research/candidates/{candidates[0]['id']}/approve").json()
    assert product["sku"].startswith("SKU-")

    attached = client.post(
        f"/products/{product['id']}/supplier",
        json={
            "supplier": "home_depot",
            "source_url": "https://www.homedepot.com/p/example",
            "last_price": 49.97,
            "last_shipping": 0,
            "in_stock": True,
        },
    ).json()
    assert attached["status"] == "monitoring"
    assert attached["supplier_products"][0]["last_price"] == 49.97

    repricing = client.post("/repricing/run").json()
    assert repricing["updated"] == 1
    assert repricing["snapshots"][0]["floor_price"] is not None
    assert repricing["snapshots"][0]["suggested_price"] >= repricing["snapshots"][0]["floor_price"]


def test_saved_research_sellers_can_be_upserted_listed_and_deleted(client) -> None:
    created = client.post(
        "/research/sellers",
        json={"username": "@Tweed&Till", "seed_listing_url": "https://www.ebay.com/str/tweedtill"},
    )

    assert created.status_code == 200
    seller = created.json()
    assert seller["username"] == "Tweed&Till"
    assert seller["seed_listing_url"] == "https://www.ebay.com/str/tweedtill"
    assert seller["notes"] is None

    updated = client.post("/research/sellers", json={"username": "tweed&till", "notes": "Watch their flooring drops"})
    assert updated.status_code == 200
    assert updated.json()["id"] == seller["id"]
    assert updated.json()["notes"] == "Watch their flooring drops"
    assert updated.json()["seed_listing_url"] == "https://www.ebay.com/str/tweedtill"

    sellers = client.get("/research/sellers").json()
    assert [item["username"] for item in sellers] == ["Tweed&Till"]

    deleted = client.delete("/research/sellers/tweed%26till")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert client.get("/research/sellers").json() == []


def test_orders_and_fulfillment_update(client) -> None:
    order = client.post("/orders/sync-sandbox").json()
    assert order["ebay_order_id"] == "SANDBOX-ORDER-001"
    assert order["account_id"] == "sandbox"
    task_id = order["fulfillment_tasks"][0]["id"]

    updated = client.patch(
        f"/fulfillment-tasks/{task_id}",
        json={"status": "in_progress", "note": "Checking supplier availability"},
    ).json()
    assert updated["status"] == "in_progress"

    orders = client.get("/orders?include_sandbox=true").json()
    assert len(orders) == 1


def test_ebay_connection_reports_missing_credentials(client) -> None:
    connection = client.get("/ebay/connection").json()

    assert connection["environment"] == "sandbox"
    assert connection["configured"] is False
    assert connection["connected"] is False
    assert connection["writes_enabled"] is False
    assert "Ebay Client ID" not in connection["missing"]
    assert "eBay Client ID" in connection["missing"]
    assert connection["api_base_url"] == "https://api.sandbox.ebay.com"
    assert connection["token_url"] == "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
    assert "sell.inventory.readonly" in " ".join(connection["scopes"])


def test_ebay_account_profiles_store_multiple_accounts_without_echoing_secret(client) -> None:
    first = client.post(
        "/ebay/accounts",
        json={
            "label": "Buyclassy Sandbox",
            "account_id": "buyclassy-sandbox",
            "environment": "sandbox",
            "client_id": "SANDBOX-CLIENT-ID",
            "client_secret": "SANDBOX-SECRET",
            "redirect_uri": "MakSandbox-RuName",
            "category_id": "9355",
            "merchant_location_key": "warehouse-1",
            "fulfillment_policy_id": "fulfillment-policy",
            "payment_policy_id": "payment-policy",
            "return_policy_id": "return-policy",
        },
    )
    assert first.status_code == 200
    account = first.json()
    assert account["key"] == "buyclassy-sandbox"
    assert account["configured"] is True
    assert account["connected"] is False
    assert "client_secret" not in account
    assert account["missing"] == []

    second = client.post(
        "/ebay/accounts",
        json={"label": "Outlet Sandbox", "account_id": "outlet-sandbox", "environment": "sandbox"},
    ).json()
    assert second["configured"] is True
    assert second["missing"] == []

    updated = client.patch(
        f"/ebay/accounts/{second['key']}",
        json={
            "label": "Outlet Sandbox",
            "account_id": "outlet-sandbox",
            "environment": "sandbox",
            "access_token": "ACCESS-TOKEN",
            "refresh_token": "REFRESH-TOKEN",
        },
    ).json()
    assert updated["connected"] is True
    assert updated["configured"] is True

    accounts = client.get("/ebay/accounts").json()
    assert {item["account_id"] for item in accounts} == {"buyclassy-sandbox", "outlet-sandbox"}
    assert all("client_secret" not in item for item in accounts)

    stats = client.get("/stats/overview?range=all&grain=day&account=buyclassy-sandbox").json()
    assert "buyclassy-sandbox" in stats["available_accounts"]
    assert "outlet-sandbox" in stats["available_accounts"]

    deleted = client.delete(f"/ebay/accounts/{second['key']}").json()
    assert deleted["deleted"] is True
    assert {item["account_id"] for item in client.get("/ebay/accounts").json()} == {"buyclassy-sandbox"}


def test_ebay_sync_run_blocks_when_browser_account_mismatches_selected_store(client) -> None:
    account = client.post(
        "/ebay/accounts",
        json={"label": "Main Store", "account_id": "a.m.anim-59", "environment": "production"},
    ).json()
    client.post(
        "/ebay/browser-account",
        json={
            "account_key": account["key"],
            "detected_username": "wrong-store",
            "url": "https://www.ebay.com/sh/ovw",
            "marketplace": "EBAY_US",
        },
    )

    run = client.post("/ebay/sync-runs", json={"account_key": account["key"]}).json()

    assert run["status"] == "needs_review"
    assert run["phase"] == "account_check"
    assert "wrong-store" in run["message"]
    assert "a.m.anim-59" in run["message"]


def test_ebay_listing_report_sync_reconciles_one_store(client) -> None:
    account = client.post(
        "/ebay/accounts",
        json={"label": "Main Store", "account_id": "a.m.anim-59", "environment": "production"},
    ).json()
    client.post(
        "/ebay/browser-account",
        json={
            "account_key": account["key"],
            "detected_username": "a.m.anim-59",
            "url": "https://www.ebay.com/sh/ovw",
            "marketplace": "EBAY_US",
        },
    )
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Sync-Known/123",
            "title": "Sync Known Product",
            "source_price": 11.0,
            "source_shipping": 0.0,
            "description": "Known report sync product",
            "image_urls": "https://images.thdstatic.com/productImages/sync-known.jpg",
        },
    ).json()
    client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "OLD-MISSING-1", "account_id": account["key"], "environment": "manual", "quantity": 1, "status": "active"},
    )
    started = client.post("/ebay/sync-runs", json={"account_key": account["key"]}).json()
    assert started["status"] == "running"
    assert started["phase"] == "opening_reports"
    assert f"autozs_sync_run={started['id']}" in started["runner_url"]
    assert "autozs_account_key=main-store" in started["runner_url"]
    progress = client.patch(
        f"/ebay/sync-runs/{started['id']}",
        json={"phase": "waiting_for_report", "report_reference": "13311151689", "increment_attempts": True},
    ).json()
    assert progress["report_reference"] == "13311151689"
    assert progress["attempts"] == 1

    synced = client.post(
        "/ebay/sync-runs/listing-report",
        json={
            "account_key": account["key"],
            "run_id": started["id"],
            "rows": [
                {
                    "listing_id": "KNOWN-1",
                    "sku": product["sku"],
                    "title": "Sync Known Product",
                    "price": "$29.99",
                    "quantity": "4",
                    "status": "Active",
                },
                {
                    "item_id": "SCHEDULED-UNKNOWN-1",
                    "title": "Unknown Scheduled Listing",
                    "current_price": "19.95",
                    "available_quantity": "1",
                    "listing_status": "Scheduled",
                    "views": "0",
                    "renews_on": "Wed, Jul 29, 2026",
                },
            ],
        },
    ).json()

    assert synced["status"] == "completed"
    assert synced["listings_seen"] == 2
    assert synced["listings_upserted"] == 2
    assert synced["listings_imported"] == 1
    assert synced["listings_tombstoned"] == 1

    listings = {item["listing_id"]: item for item in client.get("/ebay/listings").json()}
    assert listings["KNOWN-1"]["product_id"] == product["id"]
    assert listings["KNOWN-1"]["price"] == 29.99
    assert listings["KNOWN-1"]["views"] == 0
    assert listings["SCHEDULED-UNKNOWN-1"]["status"] == "scheduled"
    assert listings["SCHEDULED-UNKNOWN-1"]["renews_at"].startswith("2026-07-29")
    assert listings["OLD-MISSING-1"]["status"] == "tombstoned"

    stats = client.get(f"/stats/overview?range=all&grain=day&account={account['key']}").json()
    assert stats["totals"]["active_listings"] == 2
    assert stats["totals"]["listed_value"] == 49.94


def test_ebay_oauth_start_builds_sandbox_authorization_url(client) -> None:
    client.patch(
        "/settings/pricing",
        json={
            "ebay_environment": "sandbox",
            "ebay_client_id": "SANDBOX-CLIENT-ID",
            "ebay_client_secret": "SANDBOX-SECRET",
            "ebay_redirect_uri": "MakSandbox-RuName",
        },
    )

    started = client.post("/ebay/oauth/start").json()

    assert started["environment"] == "sandbox"
    assert started["state"]
    assert started["authorization_url"].startswith("https://auth.sandbox.ebay.com/oauth2/authorize?")
    assert "client_id=SANDBOX-CLIENT-ID" in started["authorization_url"]
    assert "redirect_uri=MakSandbox-RuName" in started["authorization_url"]
    assert "response_type=code" in started["authorization_url"]
    assert "sell.inventory.readonly" in started["authorization_url"]

    connection = client.get("/ebay/connection").json()
    assert connection["configured"] is True
    assert connection["connected"] is False
    assert started["state"] in connection["auth_url"]


def test_ebay_oauth_callback_exchanges_code_and_stores_tokens(client, monkeypatch) -> None:
    client.patch(
        "/settings/pricing",
        json={
            "ebay_environment": "sandbox",
            "ebay_client_id": "SANDBOX-CLIENT-ID",
            "ebay_client_secret": "SANDBOX-SECRET",
            "ebay_redirect_uri": "MakSandbox-RuName",
        },
    )
    started = client.post("/ebay/oauth/start").json()
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return httpx.Response(
            200,
            json={
                "access_token": "ACCESS-TOKEN",
                "expires_in": 7200,
                "refresh_token": "REFRESH-TOKEN",
                "refresh_token_expires_in": 47304000,
                "token_type": "User Access Token",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(ebay.httpx, "post", fake_post)

    exchanged = client.post("/ebay/oauth/callback", json={"code": "AUTH-CODE", "state": started["state"]}).json()

    assert exchanged["environment"] == "sandbox"
    assert exchanged["connected"] is True
    assert exchanged["access_token_expires_at"]
    assert exchanged["refresh_token_expires_at"]
    assert calls[0]["url"] == "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
    assert calls[0]["data"] == {
        "grant_type": "authorization_code",
        "code": "AUTH-CODE",
        "redirect_uri": "MakSandbox-RuName",
    }
    expected_auth = base64.b64encode(b"SANDBOX-CLIENT-ID:SANDBOX-SECRET").decode("ascii")
    assert calls[0]["headers"]["Authorization"] == f"Basic {expected_auth}"

    settings = client.get("/settings").json()
    assert settings["ebay_access_token"] == "ACCESS-TOKEN"
    assert settings["ebay_refresh_token"] == "REFRESH-TOKEN"
    assert settings["ebay_token_expires_at"]
    assert settings["ebay_refresh_token_expires_at"]
    assert client.get("/ebay/connection").json()["connected"] is True


def test_ebay_oauth_callback_rejects_state_mismatch(client) -> None:
    client.patch(
        "/settings/pricing",
        json={
            "ebay_environment": "sandbox",
            "ebay_client_id": "SANDBOX-CLIENT-ID",
            "ebay_client_secret": "SANDBOX-SECRET",
            "ebay_redirect_uri": "MakSandbox-RuName",
        },
    )
    client.post("/ebay/oauth/start")

    response = client.post("/ebay/oauth/callback", json={"code": "AUTH-CODE", "state": "wrong-state"})

    assert response.status_code == 400
    assert "state did not match" in response.json()["detail"]


def test_ebay_oauth_refresh_renews_access_token(client, monkeypatch) -> None:
    client.patch(
        "/settings/pricing",
        json={
            "ebay_environment": "sandbox",
            "ebay_client_id": "SANDBOX-CLIENT-ID",
            "ebay_client_secret": "SANDBOX-SECRET",
            "ebay_redirect_uri": "MakSandbox-RuName",
            "ebay_refresh_token": "REFRESH-TOKEN",
            "ebay_refresh_token_expires_at": "2027-01-01T00:00:00+00:00",
        },
    )
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return httpx.Response(
            200,
            json={"access_token": "NEW-ACCESS-TOKEN", "expires_in": 7200, "token_type": "User Access Token"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(ebay.httpx, "post", fake_post)

    refreshed = client.post("/ebay/oauth/refresh").json()

    assert refreshed["connected"] is True
    assert refreshed["access_token_expires_at"]
    assert refreshed["refresh_token_expires_at"] == "2027-01-01T00:00:00+00:00"
    assert calls[0]["data"]["grant_type"] == "refresh_token"
    assert calls[0]["data"]["refresh_token"] == "REFRESH-TOKEN"
    assert "sell.inventory.readonly" in calls[0]["data"]["scope"]
    settings = client.get("/settings").json()
    assert settings["ebay_access_token"] == "NEW-ACCESS-TOKEN"


def test_sandbox_order_maps_to_product_and_account_stats(client) -> None:
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Order-Mapped/123",
            "title": "Order Mapped Product",
            "source_price": 20.0,
            "source_shipping": 0.0,
            "description": "Order mapping test",
            "image_urls": "https://images.thdstatic.com/productImages/order-mapped.jpg",
        },
    ).json()

    order = client.post("/orders/sync-sandbox").json()
    assert order["account_id"] == "sandbox"
    assert order["items"][0]["product_id"] == product["id"]
    assert order["items"][0]["title"] == product["title"]

    stats = client.get("/stats/overview?range=all&grain=day&account=sandbox").json()
    assert "sandbox" in stats["available_accounts"]
    assert stats["totals"]["order_revenue"] == 79.99


def test_stats_overview_reports_listed_products_by_account(client) -> None:
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Stats-Listed/123",
            "title": "Stats Listed Product",
            "source_price": 17.97,
            "source_shipping": 0.0,
            "competitor_price": 21.49,
            "description": "Stats listed product",
            "image_urls": (
                "data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
            ),
        },
    ).json()
    marked = client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "STAT-LIST-1", "account_id": "Buyclassy-Us", "environment": "manual", "quantity": 1, "status": "listed"},
    ).json()

    stats = client.get("/stats/overview?range=all&grain=day&account=Buyclassy-Us").json()

    assert "Buyclassy-Us" in stats["available_accounts"]
    assert stats["selected_account"] == "Buyclassy-Us"
    assert stats["totals"]["active_listings"] == 1
    assert stats["totals"]["listed_value"] == marked["price"]
    assert stats["totals"]["order_revenue"] == 0


def test_import_source_product_creates_listing_draft_and_images(client) -> None:
    url = (
        "https://www.homedepot.com/p/HDX-13-Gallon-Reinforced-Top-Drawstring-Fresh-Scented-"
        "Tall-Kitchen-Trash-Bags-with-20-PCR-200-Count-HDR13XHFN200W-F/331012931"
    )
    response = client.post(
        "/products/import",
        json={"urls": url, "source_price_override": 17.97, "competitor_price": 21.49},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    product = body["products"][0]
    assert product["supplier_products"][0]["source_url"] == url
    assert product["supplier_products"][0]["last_price"] == 17.97
    assert product["listing_drafts"][0]["calculated_price"] == 25.44
    assert product["listing_drafts"][0]["title"].startswith("13 Gallon")
    assert product["listing_drafts"][0]["title"].endswith("| FREE SHIPPING")
    assert product["images"]


def test_import_normalizes_internal_auto_import_query_params(client) -> None:
    clean_url = "https://www.homedepot.com/p/Auto-Import-Normalized/123?MERCH=REC"
    flagged_url = "https://www.homedepot.com/p/Auto-Import-Normalized/123?ea_auto_import=1&MERCH=REC&auto_download_test=1"

    first = client.post(
        "/products/import",
        json={"urls": flagged_url, "source_price_override": 12.5},
    ).json()["products"][0]
    second = client.post(
        "/products/import",
        json={"urls": clean_url, "source_price_override": 13.5},
    ).json()["products"][0]

    assert first["id"] == second["id"]
    assert second["supplier_products"][0]["source_url"] == clean_url
    assert "ea_auto_import" not in second["supplier_products"][0]["source_url"]
    assert "auto_download_test" not in second["supplier_products"][0]["source_url"]
    assert second["supplier_products"][0]["last_price"] == 13.5


def test_delete_hides_product_but_reimport_revives_cached_source_data(client) -> None:
    url = "https://www.homedepot.com/p/Cached-Product/777"
    imported = client.post(
        "/products/import",
        json={"urls": url, "source_price_override": 25.0, "source_shipping_override": 5.0},
    ).json()
    product = imported["products"][0]
    product_id = product["id"]
    assert product["supplier_products"][0]["last_price"] == 25.0
    assert product["supplier_products"][0]["last_shipping"] == 5.0

    deleted = client.delete(f"/products/{product_id}").json()
    assert deleted["status"] == "deleted"
    assert all(item["id"] != product_id for item in client.get("/products").json())
    assert any(item["id"] == product_id for item in client.get("/products?include_deleted=true").json())

    revived = client.post("/products/import", json={"urls": url}).json()["products"][0]
    assert revived["id"] == product_id
    assert revived["status"] == "monitoring"
    assert revived["supplier_products"][0]["last_price"] == 25.0
    assert revived["supplier_products"][0]["last_shipping"] == 5.0
    assert revived["listing_drafts"][0]["calculated_price"] is not None

    history = client.get(f"/products/{product_id}/price-history").json()
    supplier_history = [snapshot for snapshot in history if snapshot["source"] == "supplier"]
    assert len(supplier_history) >= 2
    assert supplier_history[0]["price"] == 25.0
    assert supplier_history[0]["shipping"] == 5.0


def test_reimport_after_browser_capture_keeps_cached_price_and_images(client, monkeypatch) -> None:
    url = "https://www.homedepot.com/p/Cached-Capture-Product/331012931"
    monkeypatch.setattr(
        importer,
        "_download_image",
        lambda product_id, image_url, sort_order: f"downloads/product_images/{product_id}/{sort_order + 1:02d}.jpg",
    )
    captured = client.post(
        "/products/import-captured",
        json={
            "source_url": url,
            "title": "Cached Capture Product",
            "source_price": 17.97,
            "source_shipping": 0.0,
            "description": "Captured product details",
            "image_urls": (
                "https://images.thdstatic.com/productImages/cached-front.jpg\n"
                "https://images.thdstatic.com/productImages/cached-side.jpg"
            ),
        },
    ).json()

    def blocked_source_fetch(source_url: str, source_price_override: float | None = None) -> importer.ImportedProductData:
        return importer.ImportedProductData(
            source_url=source_url,
            supplier="home_depot",
            supplier_sku="331012931",
            title="Cached Capture Product",
            source_price=None,
            description="Fallback description",
            image_urls=["https://images.thdstatic.com/productImages/331012931.jpg"],
            warnings=[
                "Home Depot blocked server-side price capture; use browser capture or fill source price in Products",
                "Image URL was inferred from the Home Depot product id",
                "No source price captured; margin and draft price need source price before listing",
            ],
        )

    monkeypatch.setattr(importer, "extract_product_data", blocked_source_fetch)
    reimported = client.post("/products/import", json={"urls": url}).json()
    product = reimported["products"][0]

    assert product["id"] == captured["id"]
    assert product["supplier_products"][0]["last_price"] == 17.97
    assert [image["image_url"] for image in product["images"]] == [image["image_url"] for image in captured["images"]]
    assert "No source price captured" not in " ".join(reimported["warnings"])
    assert "Image URL was inferred" not in " ".join(reimported["warnings"])


def test_source_refresh_queue_prioritizes_missing_price_and_low_profit(client) -> None:
    missing = client.post(
        "/products/import",
        json={"urls": "https://www.homedepot.com/p/Missing-Price/111"},
    ).json()["products"][0]
    profitable = client.post(
        "/products/import",
        json={"urls": "https://www.homedepot.com/p/Profitable/222", "source_price_override": 50.0, "source_shipping_override": 0.0},
    ).json()["products"][0]
    low_profit = client.post(
        "/products/import",
        json={
            "urls": "https://www.homedepot.com/p/Low-Profit/333",
            "source_price_override": 17.97,
            "source_shipping_override": 0.0,
            "competitor_price": 21.49,
        },
    ).json()["products"][0]
    client.patch("/settings/pricing", json={"default_pricing_strategy": "competitor", "default_round_to_99": True})
    client.post("/products/recalculate-drafts")

    queue = client.get("/repricing/source-refresh-queue").json()
    assert queue["total"] == 3
    assert queue["needs_refresh"] == 2
    items = {item["product_id"]: item for item in queue["items"]}
    assert items[missing["id"]]["priority"] == "high"
    assert items[missing["id"]]["reason"] == "Missing source price"
    assert items[missing["id"]]["extension_ready"] is True
    assert items[low_profit["id"]]["priority"] == "medium"
    assert "below minimum" in items[low_profit["id"]]["reason"]
    assert items[profitable["id"]]["priority"] == "low"


def test_source_capture_queue_lists_imports_that_need_browser_capture(client) -> None:
    missing = client.post(
        "/products/import",
        json={"urls": "https://www.homedepot.com/p/Capture-Queue-Missing/111"},
    ).json()["products"][0]
    ready = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Capture-Queue-Ready/222",
            "title": "Capture Queue Ready",
            "source_price": 10.0,
            "source_shipping": 0.0,
            "description": "Ready source capture",
            "image_urls": (
                "data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
            ),
        },
    ).json()

    queue = client.get("/products/capture-queue").json()

    assert queue["total"] == 1
    assert queue["items"][0]["product_id"] == missing["id"]
    assert queue["items"][0]["source_url"] == missing["supplier_products"][0]["source_url"]
    assert queue["items"][0]["item_specifics"]["Brand"] == "Capture Queue Missing"
    assert queue["items"][0]["item_specifics"]["MPN"] == "111"
    assert "source price" in queue["items"][0]["missing"]
    assert "source shipping" in queue["items"][0]["missing"]
    assert any(label in queue["items"][0]["missing"] for label in ["images", "downloaded images"])
    assert all(item["product_id"] != ready["id"] for item in queue["items"])


def test_stats_overview_reports_catalog_profit_and_mix(client) -> None:
    client.post(
        "/products/import",
        json={"urls": "https://www.homedepot.com/p/Stats-Free/111", "source_price_override": 10.0, "source_shipping_override": 0.0},
    )
    client.post(
        "/products/import",
        json={"urls": "https://www.homedepot.com/p/Stats-Paid/222", "source_price_override": 20.0, "source_shipping_override": 5.0},
    )
    client.post("/orders/sync-sandbox")

    stats = client.get("/stats/overview?range=all&grain=day&account=sandbox").json()

    assert stats["selected_account"] == "sandbox"
    assert stats["totals"]["imported_products"] == 2
    assert stats["totals"]["catalog_revenue"] == 49.56
    assert stats["totals"]["catalog_cost"] == 35.0
    assert stats["totals"]["catalog_fees"] == 7.56
    assert stats["totals"]["expected_profit"] == 7.0
    assert stats["totals"]["low_profit_products"] == 2
    assert stats["totals"]["order_revenue"] == 79.99
    assert {item["label"]: item["value"] for item in stats["shipping_mix"]} == {"Free": 1, "Paid": 1, "Unknown": 0}
    assert {item["label"]: item["value"] for item in stats["pipeline_mix"]}["Images"] == 2
    assert {item["label"]: item["value"] for item in stats["listing_readiness_mix"]} == {"Manual ready": 0, "API ready": 0, "Needs work": 2}
    assert stats["series"]
    assert stats["series"][0]["fees"] == 7.56
    assert stats["import_series"][0]["count"] == 2
    assert stats["top_products"][0]["expected_profit"] >= stats["top_products"][1]["expected_profit"]


def test_stats_overview_uses_enabled_gift_card_discount(client) -> None:
    client.patch(
        "/settings/pricing",
        json={"default_gift_card_discount_enabled": True, "default_gift_card_discount_percent": 6.0},
    )
    client.post(
        "/products/import",
        json={"urls": "https://example.com/p/Gift-Card-Stats/1", "source_price_override": 100.0, "source_shipping_override": 0.0},
    )

    stats = client.get("/stats/overview?range=all&grain=day&account=all").json()

    assert stats["totals"]["catalog_cost"] == 94.0
    assert stats["totals"]["expected_profit"] > 0


def test_partial_image_downloads_stay_in_image_pipeline(client, monkeypatch) -> None:
    monkeypatch.setattr(
        importer,
        "_download_image",
        lambda product_id, image_url, sort_order: f"downloads/product_images/{product_id}/{sort_order + 1:02d}.jpg"
        if sort_order == 0
        else None,
    )
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Partial-Images/444",
            "title": "Partial Images Product",
            "source_price": 20.0,
            "source_shipping": 0.0,
            "description": "Partial image test\nFirst image downloads\nSecond image still URL only",
            "image_urls": "https://images.thdstatic.com/productImages/partial-front.jpg\nhttps://images.thdstatic.com/productImages/partial-side.jpg",
        },
    ).json()

    assert [bool(image["local_path"]) for image in product["images"]] == [True, False]
    stats = client.get("/stats/overview?range=all&grain=day&account=all").json()
    assert {item["label"]: item["value"] for item in stats["pipeline_mix"]}["Images"] == 1

    readiness = client.get(f"/products/{product['id']}/listing-readiness").json()
    assert readiness["manual_ready"] is False
    assert "all product images downloaded" in readiness["missing_manual"]
    assert any("Only 1/2 image" in warning for warning in readiness["warnings"])

    package = client.get(f"/products/{product['id']}/ebay-package").json()
    assert package["manual_image_paths"] == [product["images"][0]["local_path"]]
    assert package["image_upload_status"] == "missing_downloads"


def test_captured_import_preserves_unknown_shipping(client) -> None:
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Unknown-Shipping/123",
            "title": "Unknown Shipping Product",
            "source_price": 20.0,
            "description": "Shipping was not visible",
            "image_urls": "https://images.thdstatic.com/productImages/unknown-front.jpg",
        },
    ).json()

    assert product["supplier_products"][0]["last_shipping"] == -1.0
    stats = client.get("/stats/overview?range=all&grain=day&account=all").json()
    assert {item["label"]: item["value"] for item in stats["shipping_mix"]} == {"Free": 0, "Paid": 0, "Unknown": 1}
    assert {item["label"]: item["value"] for item in stats["pipeline_mix"]}["Shipping"] == 1

    readiness = client.get(f"/products/{product['id']}/listing-readiness").json()
    assert readiness["manual_ready"] is False
    assert "supplier/source shipping" in readiness["missing_manual"]

    queue = client.get("/repricing/source-refresh-queue").json()
    queue_item = next(item for item in queue["items"] if item["product_id"] == product["id"])
    assert queue_item["priority"] == "high"
    assert queue_item["reason"] == "Missing source shipping"


def test_captured_import_stores_subscription_discount_separate_from_shipping(client) -> None:
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Subscription-Discount/123",
            "title": "Subscription Discount Product",
            "source_price": 20.0,
            "source_shipping": 0.0,
            "subscription_discount_percent": 5.0,
            "description": "Subscribe and get discount capture test",
            "image_urls": "https://images.thdstatic.com/productImages/subscription-front.jpg",
        },
    ).json()

    supplier = product["supplier_products"][0]
    assert supplier["last_price"] == 20.0
    assert supplier["last_shipping"] == 0.0
    assert supplier["subscription_discount_percent"] == 5.0


def test_pricing_settings_update_changes_imported_listing_price(client) -> None:
    settings = client.patch("/settings/pricing", json={"default_margin_percent": 0.10, "default_ebay_fee_rate": 0.10}).json()
    assert settings["default_margin_percent"] == 0.10

    response = client.post(
        "/products/import",
        json={"urls": "https://example.com/p/Test-Product/123", "source_price_override": 10.0},
    )
    draft = response.json()["products"][0]["listing_drafts"][0]
    assert draft["calculated_price"] == 12.5


def test_theme_setting_syncs_across_app_surfaces(client) -> None:
    settings = client.get("/settings").json()
    assert settings["ui_theme"] == "system"

    updated = client.patch("/settings/theme", json={"ui_theme": "dark"}).json()
    assert updated["ui_theme"] == "dark"
    assert client.get("/settings").json()["ui_theme"] == "dark"


def test_catalog_settings_persist_and_validate_structured_sections(client) -> None:
    updated = client.patch(
        "/settings/catalog",
        json={
            "supplier_settings_json": '{"home_depot":{"default_quantity":3}}',
            "keyword_blacklist_json": '["hazmat","prescription"]',
            "buyer_accounts_json": (
                '[{"id":"buyer-1","label":"Home Depot buyer","supplier":"home_depot",'
                '"username":"buyer@example.com","connection_mode":"browser","status":"sign_in_needed",'
                '"region":"United States","payment_method":"credit_card","max_pending_orders":"5",'
                '"daily_order_limit":"300","auto_tracking":true,'
                '"password":"must-not-save"}]'
            ),
            "notifications_order_updates": False,
            "notifications_email": "alerts@example.com",
        },
    )

    assert updated.status_code == 200
    settings = updated.json()
    assert settings["supplier_settings_json"] == '{"home_depot":{"default_quantity":3}}'
    assert settings["keyword_blacklist_json"] == '["hazmat","prescription"]'
    assert "must-not-save" not in settings["buyer_accounts_json"]
    buyer_accounts = json.loads(settings["buyer_accounts_json"])
    assert buyer_accounts[0]["payment_method"] == "credit_card"
    assert buyer_accounts[0]["auto_tracking"] is True
    assert settings["notifications_order_updates"] is False
    assert settings["notifications_email"] == "alerts@example.com"

    invalid = client.patch("/settings/catalog", json={"keyword_blacklist_json": '{"not":"a list"}'})
    assert invalid.status_code == 422


def test_keyword_blacklist_blocks_matching_product_import(client) -> None:
    client.patch("/settings/catalog", json={"keyword_blacklist_json": '["blocked product"]'})

    imported = client.post(
        "/products/import",
        json={"urls": "https://example.com/p/Blocked-Product/123", "source_price_override": 10.0},
    ).json()

    assert imported["imported"] == 0
    assert imported["products"] == []
    assert "blocked by keyword blacklist" in imported["warnings"][0]


def test_description_template_and_supplier_quantity_apply_to_listing_package(client) -> None:
    client.patch(
        "/settings/catalog",
        json={
            "supplier_settings_json": '{"home_depot":{"default_quantity":4}}',
            "description_template_enabled": True,
            "description_template_name": "Makai Home Supply",
            "description_template_brand": "Makai Store",
            "description_template_about": "Helpful home improvement products.",
        },
    )
    product = client.post(
        "/products/import",
        json={
            "urls": "https://www.homedepot.com/p/Template-Test/444",
            "source_price_override": 20.0,
            "source_shipping_override": 0.0,
        },
    ).json()["products"][0]
    client.patch(
        f"/products/{product['id']}/capture",
        json={"description": "Strong construction\nEasy to use"},
    )

    package = client.get(f"/products/{product['id']}/ebay-package").json()
    assert package["quantity"] == 4
    assert 'data-autozs-template="1"' in package["description"]
    assert "Makai Store" in package["description"]
    assert "Makai Home Supply" in package["description"]
    assert "Strong construction" in package["description"]


def test_source_refresh_interval_setting_drives_queue_default(client) -> None:
    product = client.post(
        "/products/import",
        json={
            "urls": "https://www.homedepot.com/p/Refresh-Interval/123",
            "source_price_override": 100.0,
            "source_shipping_override": 0.0,
        },
    ).json()["products"][0]

    updated = client.patch("/settings/pricing", json={"source_refresh_interval_days": 3}).json()
    assert updated["source_refresh_interval_days"] == 3.0

    queue = client.get("/repricing/source-refresh-queue").json()
    assert queue["stale_after_days"] == 3
    item = next(item for item in queue["items"] if item["product_id"] == product["id"])
    assert item["reason"] == "Fresh enough"


def test_recalculate_drafts_applies_current_settings_to_existing_products(client) -> None:
    imported = client.post(
        "/products/import",
        json={"urls": "https://example.com/p/Recalculate-Product/222", "source_price_override": 10.0},
    ).json()
    product_id = imported["products"][0]["id"]
    assert imported["products"][0]["listing_drafts"][0]["calculated_price"] == 14.16

    client.patch(
        "/settings/pricing",
        json={
            "default_margin_percent": 0.50,
            "default_ebay_fee_rate": 0.10,
            "default_return_risk_rate": 0.0,
            "default_pricing_strategy": "margin",
            "default_round_to_99": False,
        },
    )
    recalculated = client.post("/products/recalculate-drafts").json()
    product = next(item for item in recalculated["products"] if item["id"] == product_id)
    assert recalculated["updated"] == 1
    assert product["listing_drafts"][0]["calculated_price"] == 16.67


def test_margin_recalculation_coalesces_scheduled_ebay_price_revision_jobs(client) -> None:
    imported = client.post(
        "/products/import",
        json={
            "urls": "https://example.com/p/Scheduled-Reprice/333",
            "source_price_override": 10.0,
            "source_shipping_override": 0.0,
        },
    ).json()
    product_id = imported["products"][0]["id"]
    original_price = imported["products"][0]["listing_drafts"][0]["calculated_price"]
    listing = client.post(
        f"/products/{product_id}/mark-listed",
        json={
            "listing_id": "800000000333",
            "account_id": "main-store",
            "environment": "production",
            "quantity": 1,
            "status": "scheduled",
        },
    ).json()
    assert listing["price"] == original_price

    client.patch(
        "/settings/pricing",
        json={
            "default_margin_percent": 0.50,
            "default_ebay_fee_rate": 0.10,
            "default_return_risk_rate": 0.0,
            "default_pricing_strategy": "margin",
            "default_round_to_99": False,
        },
    )
    first = client.post("/products/recalculate-drafts").json()
    assert first["revision_jobs_queued"] == 1
    assert first["revision_jobs_updated"] == 0
    jobs = client.get("/ebay/revision-jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "needs_review"
    assert jobs[0]["approval_required"] is True
    assert jobs[0]["guard_passed"] is True
    assert jobs[0]["source_price"] == 10.0
    assert jobs[0]["projected_profit"] is not None
    assert jobs[0]["old_price"] == original_price
    assert jobs[0]["target_price"] == 16.67
    assert "autozs_workflow=revise_price" in jobs[0]["assistant_url"]
    assert "autozs_autosubmit=1" in jobs[0]["assistant_url"]

    client.patch("/settings/pricing", json={"default_margin_percent": 0.60})
    second = client.post("/products/recalculate-drafts").json()
    assert second["revision_jobs_queued"] == 0
    assert second["revision_jobs_updated"] == 1
    jobs = client.get("/ebay/revision-jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["target_price"] == 17.78
    assert jobs[0]["status"] == "needs_review"
    assert jobs[0]["approved_at"] is None

    client.post("/ebay/accounts", json={"label": "Main Store", "account_id": "main-store", "environment": "production"})
    client.post(
        "/ebay/browser-account",
        json={
            "detected_username": "main-store",
            "url": "https://www.ebay.com/sh/overview",
            "marketplace": "EBAY_US",
            "source": "test",
            "account_key": "main-store",
        },
    )
    not_approved = client.post("/ebay/revision-jobs/next")
    assert not_approved.status_code == 404
    approved = client.post(f"/ebay/revision-jobs/{jobs[0]['id']}/approve").json()
    assert approved["status"] == "queued"
    assert approved["approved_at"] is not None
    sheet = client.post(
        "/ebay/revision-sheets/prepare",
        json={
            "account_key": "main-store",
            "job_ids": [approved["id"]],
            "template_csv": "#INFO,Version=0.0.2\nAction,Item number,Start price,Quantity\n",
        },
    ).json()
    assert sheet["job_ids"] == [approved["id"]]
    assert "Revise,800000000333,17.78," in sheet["csv_content"]
    client.patch("/settings/pricing", json={"ebay_revision_execution_mode": "browser_fallback"})
    running = client.post("/ebay/revision-jobs/next").json()
    assert running["status"] == "running"
    assert running["lease_expires_at"] is not None
    assert client.post("/ebay/revision-jobs/next").json()["id"] == running["id"]
    completed = client.patch(
        f"/ebay/revision-jobs/{running['id']}",
        json={"status": "completed", "message": "eBay confirmed the revision."},
    ).json()
    assert completed["status"] == "completed"
    assert client.get("/ebay/listings").json()[0]["price"] == 17.78


def test_ebay_revision_profit_guard_blocks_approval(client) -> None:
    imported = client.post(
        "/products/import",
        json={
            "urls": "https://example.com/p/Unsafe-Reprice/334",
            "source_price_override": 20.0,
            "source_shipping_override": 0.0,
        },
    ).json()
    product_id = imported["products"][0]["id"]
    client.post(
        f"/products/{product_id}/mark-listed",
        json={
            "listing_id": "800000000334",
            "account_id": "main-store",
            "environment": "production",
            "quantity": 1,
            "status": "live",
        },
    )
    client.patch(
        "/settings/pricing",
        json={
            "default_margin_percent": 0.0,
            "default_pricing_strategy": "margin",
            "default_min_profit_guard_enabled": False,
            "default_round_to_99": False,
        },
    )
    client.post("/products/recalculate-drafts")
    client.patch(
        "/settings/pricing",
        json={"default_min_profit_guard_enabled": True, "default_min_profit": 8.0},
    )
    result = client.post(
        "/ebay/revision-jobs/enqueue",
        json={"product_ids": [product_id]},
    ).json()
    assert result["queued"] + result["updated"] == 1
    job = client.get("/ebay/revision-jobs").json()[0]
    assert job["status"] == "needs_review"
    assert job["guard_passed"] is False
    assert job["projected_profit"] < 8.0
    blocked = client.post(f"/ebay/revision-jobs/{job['id']}/approve")
    assert blocked.status_code == 409
    assert "below" in blocked.json()["detail"]


def test_ebay_revision_blocks_unknown_supplier_shipping(client) -> None:
    imported = client.post(
        "/products/import",
        json={"urls": "https://example.com/p/Unknown-Shipping/335", "source_price_override": 20.0},
    ).json()
    product_id = imported["products"][0]["id"]
    client.post(
        f"/products/{product_id}/mark-listed",
        json={
            "listing_id": "800000000335",
            "account_id": "main-store",
            "environment": "production",
            "quantity": 1,
            "status": "scheduled",
        },
    )
    client.patch("/settings/pricing", json={"default_margin_percent": 0.50})
    client.post("/products/recalculate-drafts")
    job = client.get("/ebay/revision-jobs").json()[0]
    assert job["status"] == "needs_review"
    assert job["guard_passed"] is False
    assert "shipping is unknown" in job["guard_reason"]
    assert client.post(f"/ebay/revision-jobs/{job['id']}/approve").status_code == 409


def test_competitor_pricing_strategy_and_rounding(client) -> None:
    settings = client.patch(
        "/settings/pricing",
        json={
            "default_pricing_strategy": "competitor",
            "default_round_to_99": True,
            "default_undercut_amount": 0.20,
        },
    ).json()
    assert settings["default_pricing_strategy"] == "competitor"
    assert settings["default_round_to_99"] is True

    imported = client.post(
        "/products/import",
        json={
            "urls": "https://www.homedepot.com/p/Competitor-Priced-Product/456",
            "source_price_override": 17.97,
            "competitor_price": 21.49,
        },
    ).json()
    draft = imported["products"][0]["listing_drafts"][0]
    assert draft["calculated_price"] == 21.99

    package = client.get(f"/products/{imported['products'][0]['id']}/ebay-package").json()
    assert package["pricing_strategy"] == "competitor"
    assert package["competitor_target_price"] == 21.29
    assert package["margin_price"] == 25.44
    assert package["minimum_profit_price"] == 30.64
    assert package["safe_competitor_price"] == 30.64
    assert package["fee_rate_total"] == 0.1525
    assert package["estimated_fees"] == 3.35
    assert package["estimated_profit"] == 0.67
    assert package["minimum_profit"] == 8.0
    assert package["profit_gap"] == 7.33
    assert package["meets_minimum_profit"] is False
    assert package["margin_price_profit"] == 3.59
    assert package["competitor_target_profit"] == 0.07
    assert package["minimum_profit_price_profit"] == 8.0
    assert package["safe_competitor_price_profit"] == 8.0
    assert "below minimum profit" in " ".join(package["warnings"])

    readiness = client.get(f"/products/{imported['products'][0]['id']}/listing-readiness").json()
    assert any("below minimum profit" in warning for warning in readiness["warnings"])

    margin_product = client.post(
        f"/products/{imported['products'][0]['id']}/draft-price",
        json={"mode": "margin"},
    ).json()
    assert margin_product["listing_drafts"][0]["calculated_price"] == 25.99

    margin_package = client.get(f"/products/{imported['products'][0]['id']}/ebay-package").json()
    assert margin_package["price"] == 25.99
    assert margin_package["estimated_profit"] == 4.06
    assert margin_package["meets_minimum_profit"] is False
    assert margin_package["profit_gap"] == 3.94

    minimum_profit_product = client.post(
        f"/products/{imported['products'][0]['id']}/draft-price",
        json={"mode": "minimum_profit"},
    ).json()
    assert minimum_profit_product["listing_drafts"][0]["calculated_price"] == 30.99
    minimum_profit_package = client.get(f"/products/{imported['products'][0]['id']}/ebay-package").json()
    assert minimum_profit_package["estimated_profit"] == 8.29
    assert minimum_profit_package["meets_minimum_profit"] is True
    assert minimum_profit_package["profit_gap"] == 0

    competitor_product = client.post(
        f"/products/{imported['products'][0]['id']}/draft-price",
        json={"mode": "competitor"},
    ).json()
    assert competitor_product["listing_drafts"][0]["calculated_price"] == 21.99

    safe_competitor_product = client.post(
        f"/products/{imported['products'][0]['id']}/draft-price",
        json={"mode": "safe_competitor"},
    ).json()
    assert safe_competitor_product["listing_drafts"][0]["calculated_price"] == 30.99
    safe_competitor_package = client.get(f"/products/{imported['products'][0]['id']}/ebay-package").json()
    assert safe_competitor_package["estimated_profit"] == 8.29
    assert safe_competitor_package["meets_minimum_profit"] is True


def test_pricing_rounding_cents_are_configurable(client) -> None:
    settings = client.patch(
        "/settings/pricing",
        json={
            "default_pricing_strategy": "competitor",
            "default_round_to_99": True,
            "default_rounding_cents": 0.95,
            "default_undercut_amount": 0.20,
        },
    ).json()
    assert settings["default_rounding_cents"] == 0.95

    imported = client.post(
        "/products/import",
        json={
            "urls": "https://www.homedepot.com/p/Custom-Rounded-Product/456",
            "source_price_override": 17.97,
            "competitor_price": 21.49,
        },
    ).json()
    draft = imported["products"][0]["listing_drafts"][0]
    assert draft["calculated_price"] == 21.95


def test_hdx_trash_bag_source_to_ebay_listing_package_acceptance(client) -> None:
    source_url = (
        "https://www.homedepot.com/p/HDX-13-Gallon-Reinforced-Top-Drawstring-Fresh-Scented-"
        "Tall-Kitchen-Trash-Bags-with-20-PCR-200-Count-HDR13XHFN200W-F/331012931"
    )
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    client.patch(
        "/settings/pricing",
        json={
            "default_pricing_strategy": "competitor",
            "default_round_to_99": True,
            "default_undercut_amount": 0.20,
        },
    )
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": source_url,
            "title": "HDX 13 Gallon Reinforced Top Drawstring Fresh Scented Tall Kitchen Trash Bags 200 Count",
            "source_price": 17.97,
            "source_shipping": 0.0,
            "competitor_price": 21.49,
            "description": "Fresh scented kitchen trash bags\nReinforced drawstring top\n200 count box",
            "image_urls": tiny_png,
        },
    ).json()

    assert product["supplier_products"][0]["last_price"] == 17.97
    assert product["supplier_products"][0]["last_shipping"] == 0.0
    assert product["competitor_price"] == 21.49
    assert product["listing_drafts"][0]["calculated_price"] == 21.99

    package = client.get(f"/products/{product['id']}/ebay-package").json()
    assert package["source_url"] == source_url
    assert package["source_price"] == 17.97
    assert package["source_shipping"] == 0.0
    assert package["competitor_price"] == 21.49
    assert package["competitor_target_price"] == 21.29
    assert package["price"] == 21.99
    assert package["pricing_strategy"] == "competitor"
    assert package["image_upload_status"] == "ready"
    assert package["manual_image_paths"]
    assert not package["title"].startswith("HDX ")
    assert package["title"].endswith("| FREE SHIPPING")
    assert package["item_specifics"]["Brand"] == "HDX"
    assert package["item_specifics"]["MPN"] == "HDR13XHFN200W-F"
    assert "<h3>Overview</h3>" in package["description"]
    assert "<li>Reinforced drawstring top</li>" in package["description"]
    assert package["estimated_profit"] == 0.67
    assert package["meets_minimum_profit"] is False
    assert package["warnings"]

    macro = client.get(f"/products/{product['id']}/ebay-manual-macro").json()
    assert macro["manual_ready"] is True
    assert macro["missing_manual"] == []
    assert "listing.title" in macro["script"]
    assert "fillItemSpecific" in macro["script"]
    assert "Item specifics fill results" in macro["script"]
    assert "manual_image_paths" in macro["script"]

    queue = client.get("/listings/queue").json()
    listing_item = next(item for item in queue if item["product_id"] == product["id"])
    assert listing_item["manual_ready"] is True
    assert listing_item["price"] == 21.99
    assert listing_item["image_upload_status"] == "ready"
    assert listing_item["meets_minimum_profit"] is False

    marked = client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "EBAY-HDX-001", "account_id": "Buyclassy-Us", "environment": "manual", "quantity": 1, "status": "listed"},
    ).json()
    assert marked["listing_id"] == "EBAY-HDX-001"
    assert marked["account_id"] == "Buyclassy-Us"
    assert marked["price"] == 21.99
    assert marked["status"] == "listed"

    repeated = client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "EBAY-HDX-001", "account_id": "Buyclassy-Us", "environment": "production", "quantity": 2, "status": "scheduled"},
    ).json()
    assert repeated["id"] == marked["id"]
    assert repeated["environment"] == "production"
    assert repeated["quantity"] == 2
    assert repeated["status"] == "scheduled"

    listed_queue = client.get("/listings/queue").json()
    listed_item = next(item for item in listed_queue if item["product_id"] == product["id"])
    assert listed_item["listing_id"] == "EBAY-HDX-001"
    assert listed_item["listing_status"] == "scheduled"
    assert listed_item["listing_account_id"] == "Buyclassy-Us"

    ebay_listings = client.get("/ebay/listings").json()
    assert ebay_listings[0]["listing_id"] == "EBAY-HDX-001"
    assert len([listing for listing in ebay_listings if listing["listing_id"] == "EBAY-HDX-001"]) == 1

    export = client.post(f"/products/{product['id']}/export-ebay").json()
    assert export["listing_json_path"].endswith("listing.json")
    assert export["macro_script_path"].endswith("ebay_manual_macro_template.js")


def test_safe_competitor_can_be_default_import_strategy(client) -> None:
    settings = client.patch(
        "/settings/pricing",
        json={
            "default_pricing_strategy": "safe_competitor",
            "default_round_to_99": True,
            "default_undercut_amount": 0.20,
        },
    ).json()
    assert settings["default_pricing_strategy"] == "safe_competitor"

    imported = client.post(
        "/products/import",
        json={
            "urls": "https://www.homedepot.com/p/Safe-Competitor-Default/457",
            "source_price_override": 17.97,
            "competitor_price": 21.49,
        },
    ).json()
    product = imported["products"][0]
    assert product["listing_drafts"][0]["calculated_price"] == 30.99

    package = client.get(f"/products/{product['id']}/ebay-package").json()
    assert package["pricing_strategy"] == "safe_competitor"
    assert package["safe_competitor_price"] == 30.64
    assert package["meets_minimum_profit"] is True


def test_capture_update_and_ebay_package(client) -> None:
    imported = client.post(
        "/products/import",
        json={"urls": "https://www.homedepot.com/p/Test-Product/999", "source_price_override": 17.97},
    ).json()
    product_id = imported["products"][0]["id"]

    captured = client.patch(
        f"/products/{product_id}/capture",
        json={
            "title": "HDX 13 Gallon Reinforced Top Drawstring Fresh Scented Tall Kitchen Trash Bags 200 Count",
            "source_price": 17.97,
            "source_shipping": 0.0,
            "competitor_price": 21.49,
            "description": "Fresh scented kitchen trash bags\nReinforced drawstring top\n200 count box",
            "image_urls": "https://example.com/image-1.jpg\nhttps://example.com/image-2.jpg",
        },
    ).json()

    assert captured["title"].startswith("HDX 13 Gallon")
    assert captured["competitor_price"] == 21.49
    assert len(captured["images"]) >= 2
    draft_description = captured["listing_drafts"][0]["description"]
    assert "<h3>Overview</h3>" in draft_description
    assert "<h3>Highlights</h3>" in draft_description
    assert "<h3>Details</h3>" in draft_description
    assert "<li>Reinforced drawstring top</li>" in draft_description
    assert "Please review all item specifics" in draft_description
    assert "Review source details" not in draft_description

    package = client.get(f"/products/{product_id}/ebay-package").json()
    assert package["sku"] == captured["sku"]
    assert package["price"] == captured["listing_drafts"][0]["calculated_price"]
    assert package["source_price"] == 17.97
    assert package["description"] == draft_description
    assert package["title"].endswith("| FREE SHIPPING")
    assert package["manual_image_paths"] == []
    assert package["image_upload_status"] == "missing_downloads"
    assert len(package["manual_posting_steps"]) >= 5

    api_payload = client.get(f"/products/{product_id}/ebay-api-payload").json()
    assert api_payload["inventory_item_endpoint"].endswith(captured["sku"])
    assert api_payload["offer_endpoint"] == "POST /sell/inventory/v1/offer"
    assert api_payload["inventory_item_payload"]["product"]["aspects"]["Brand"] == ["HDX"]
    assert api_payload["inventory_item_payload"]["product"]["aspects"]["MPN"] == ["999"]
    assert api_payload["offer_payload"]["pricingSummary"]["price"]["value"] == str(package["price"])
    assert "ebay_category_id" in api_payload["missing_publish_requirements"]

    macro = client.get(f"/products/{product_id}/ebay-manual-macro").json()
    assert macro["manual_ready"] is False
    assert "all product images downloaded" in macro["missing_manual"]
    assert macro["price"] == package["price"]
    assert "fillIfFound" in macro["script"]
    assert "listing.title" in macro["script"]
    assert "listing.price" in macro["script"]
    assert "listing.description" in macro["script"]
    assert "listing.item_specifics" in macro["script"]
    assert "fillItemSpecific" in macro["script"]
    assert "Item specifics fill results" in macro["script"]
    assert "manual_image_paths" in macro["script"]
    assert "Source image URLs for reference only" in macro["script"]

    download = client.post(f"/products/{product_id}/download-images").json()
    assert download["attempted"] == len(captured["images"])

    export = client.post(f"/products/{product_id}/export-ebay").json()
    assert export["listing_json_path"].endswith("listing.json")
    assert export["api_payload_path"].endswith("ebay_inventory_api_payload.json")
    assert export["description_html_path"].endswith("description.html")
    assert export["macro_script_path"].endswith("ebay_manual_macro_template.js")
    assert export["zip_path"].endswith(".zip")


def test_import_captured_product_directly(client) -> None:
    client.patch(
        "/settings/pricing",
        json={"default_pricing_strategy": "competitor", "default_round_to_99": True},
    )
    response = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/HDX-Captured-Product/331012931",
            "title": "HDX Captured Product",
            "source_price": 17.97,
            "source_shipping": 5.5,
            "competitor_price": 21.49,
            "description": "Fresh scented bags\nDrawstring closure",
            "image_urls": "https://example.com/front.jpg\nhttps://example.com/back.jpg",
        },
    )
    assert response.status_code == 200
    product = response.json()
    assert product["title"] == "HDX Captured Product"
    assert product["supplier_products"][0]["supplier_sku"] == "331012931"
    assert product["supplier_products"][0]["last_shipping"] == 5.5
    assert product["listing_drafts"][0]["calculated_price"] == 21.99
    assert len(product["images"]) == 2

    package = client.get(f"/products/{product['id']}/ebay-package").json()
    assert package["source_shipping"] == 5.5
    assert package["landed_cost"] == 23.47


def test_captured_import_keeps_large_image_sets(client, monkeypatch) -> None:
    monkeypatch.setattr(importer, "_download_image", lambda product_id, image_url, sort_order: None)
    image_urls = "\n".join(f"https://images.thdstatic.com/productImages/example-{index}.jpg" for index in range(45))
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/HDX-Many-Image-Product/331012931",
            "title": "HDX Many Image Product",
            "source_price": 17.97,
            "description": "Many images capture test",
            "image_urls": image_urls,
        },
    ).json()

    assert len(product["images"]) == 45
    assert product["images"][0]["image_url"].endswith("example-0.jpg")
    assert product["images"][-1]["image_url"].endswith("example-44.jpg")

    package = client.get(f"/products/{product['id']}/ebay-package").json()
    assert len(package["image_urls"]) == 45


def test_bulk_download_missing_images_attempts_all_active_missing_images(client, monkeypatch) -> None:
    monkeypatch.setattr(importer, "_download_image", lambda product_id, image_url, sort_order: None)
    first = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Bulk-Images-One/111",
            "title": "Bulk Images One",
            "source_price": 10.0,
            "source_shipping": 0.0,
            "description": "Bulk image test",
            "image_urls": "https://images.thdstatic.com/productImages/bulk-one-front.jpg\nhttps://images.thdstatic.com/productImages/bulk-one-back.jpg",
        },
    ).json()
    second = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Bulk-Images-Two/222",
            "title": "Bulk Images Two",
            "source_price": 12.0,
            "source_shipping": 0.0,
            "description": "Bulk image test",
            "image_urls": "https://images.thdstatic.com/productImages/bulk-two-front.jpg",
        },
    ).json()

    result = client.post("/products/download-missing-images").json()

    assert result["products_checked"] == 2
    assert result["products_attempted"] == 2
    assert result["attempted"] == 3
    assert result["downloaded"] == 0
    assert {item["product_id"] for item in result["results"]} == {first["id"], second["id"]}


def test_catalog_automation_cycle_reprices_and_downloads_missing_images(client, monkeypatch) -> None:
    monkeypatch.setattr(importer, "_download_image", lambda product_id, image_url, sort_order: None)
    imported = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Catalog-Cycle/333",
            "title": "Catalog Cycle Product",
            "source_price": 17.97,
            "source_shipping": 0.0,
            "competitor_price": 21.49,
            "description": "Catalog cycle image and repricing test",
            "image_urls": "https://images.thdstatic.com/productImages/catalog-cycle-front.jpg\nhttps://images.thdstatic.com/productImages/catalog-cycle-back.jpg",
        },
    ).json()
    assert [image["local_path"] for image in imported["images"]] == [None, None]

    monkeypatch.setattr(
        importer,
        "_download_image",
        lambda product_id, image_url, sort_order: f"downloads/product_images/{product_id}/{sort_order + 1:02d}.jpg",
    )

    result = client.post("/automation/catalog-cycle").json()

    assert result["draft_prices_updated"] == 1
    assert result["repricing_snapshots"] == 1
    assert result["image_products_checked"] == 1
    assert result["image_products_attempted"] == 1
    assert result["image_download_attempted"] == 2
    assert result["image_downloaded"] == 2

    products = client.get("/products").json()
    assert products[0]["listing_drafts"][0]["calculated_price"] is not None
    assert all(image["local_path"] for image in products[0]["images"])

    runs = client.get("/automation/runs").json()
    assert len(runs) == 1
    assert runs[0]["task_name"] == "catalog_cycle"
    assert runs[0]["status"] == "completed"
    assert runs[0]["draft_prices_updated"] == result["draft_prices_updated"]
    assert runs[0]["repricing_snapshots"] == result["repricing_snapshots"]
    assert runs[0]["image_download_attempted"] == result["image_download_attempted"]
    assert runs[0]["image_downloaded"] == result["image_downloaded"]


def test_recapturing_product_replaces_stale_images(client) -> None:
    source_url = "https://www.homedepot.com/p/HDX-Recaptured-Product/331012931"
    first = client.post(
        "/products/import-captured",
        json={
            "source_url": source_url,
            "title": "HDX Recaptured Product",
            "source_price": 17.97,
            "description": "First capture",
            "image_urls": "https://example.com/old-front.jpg\nhttps://example.com/old-side.jpg",
        },
    ).json()
    assert [image["image_url"] for image in first["images"]] == [
        "https://example.com/old-front.jpg",
        "https://example.com/old-side.jpg",
    ]

    second = client.post(
        "/products/import-captured",
        json={
            "source_url": source_url,
            "title": "HDX Recaptured Product Updated",
            "source_price": 18.97,
            "description": "Second capture",
            "image_urls": "https://example.com/new-front.jpg",
        },
    ).json()
    assert [image["image_url"] for image in second["images"]] == ["https://example.com/new-front.jpg"]
    assert second["supplier_products"][0]["last_price"] == 18.97

    updated = client.patch(
        f"/products/{second['id']}/capture",
        json={
            "image_urls": "https://example.com/final-front.jpg\nhttps://example.com/final-back.jpg",
        },
    ).json()
    assert [image["image_url"] for image in updated["images"]] == [
        "https://example.com/final-front.jpg",
        "https://example.com/final-back.jpg",
    ]


def test_captured_import_normalizes_internal_auto_import_query_params(client) -> None:
    clean_url = "https://www.homedepot.com/p/HDX-Captured-Normalized/331012931?MERCH=REC"
    flagged_url = "https://www.homedepot.com/p/HDX-Captured-Normalized/331012931?MERCH=REC&ea_auto_import=1"
    first = client.post(
        "/products/import-captured",
        json={
            "source_url": flagged_url,
            "title": "HDX Captured Normalized",
            "source_price": 17.97,
            "description": "First normalized capture",
            "image_urls": "https://example.com/first.jpg",
        },
    ).json()
    second = client.post(
        "/products/import-captured",
        json={
            "source_url": clean_url,
            "title": "HDX Captured Normalized Updated",
            "source_price": 18.97,
            "description": "Second normalized capture",
            "image_urls": "https://example.com/second.jpg",
        },
    ).json()

    assert first["id"] == second["id"]
    assert second["supplier_products"][0]["source_url"] == clean_url
    assert second["supplier_products"][0]["last_price"] == 18.97
    assert [image["image_url"] for image in second["images"]] == ["https://example.com/second.jpg"]


def test_source_refresh_pilot_runs_as_a_resumable_single_item_batch(client) -> None:
    source_url = "https://www.homedepot.com/p/Refresh-Pilot/444"
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": source_url,
            "title": "Refresh Pilot Product",
            "source_price": 20.0,
            "source_shipping": 0.0,
            "description": "Refresh pilot",
            "image_urls": "https://images.thdstatic.com/productImages/refresh-pilot.jpg",
        },
    ).json()

    batch = client.post(
        "/source-refresh/batches",
        json={"limit": 5, "interval_hours": 6, "force": True},
    ).json()

    assert batch["queued"] == 1
    assert batch["due_available"] == 1
    assert batch["runner_url"].startswith(source_url)
    assert "ea_auto_import=1" in batch["runner_url"]
    assert "autozs_refresh_job=" in batch["runner_url"]
    assert batch["jobs"][0]["status"] == "running"

    refreshed = client.post(
        "/products/import-captured",
        json={
            "source_url": source_url,
            "title": "Refresh Pilot Product",
            "source_price": 21.5,
            "source_shipping": 0.0,
            "description": "Refresh pilot updated",
            "image_urls": "https://images.thdstatic.com/productImages/refresh-pilot.jpg",
            "refresh_job_id": batch["jobs"][0]["id"],
        },
    ).json()
    assert refreshed["id"] == product["id"]

    jobs = client.get(f"/source-refresh/jobs?batch_key={batch['batch_key']}").json()
    assert jobs[0]["status"] == "completed"
    assert jobs[0]["baseline_price"] == 20.0
    assert jobs[0]["captured_price"] == 21.5
    assert jobs[0]["price_changed"] is True
    assert client.post(f"/source-refresh/batches/{batch['batch_key']}/next").json() is None


def test_source_refresh_batch_only_queues_due_products_unless_forced(client) -> None:
    client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Fresh-Product/555",
            "title": "Fresh Product",
            "source_price": 10.0,
            "source_shipping": 0.0,
            "description": "Fresh product",
            "image_urls": "https://images.thdstatic.com/productImages/fresh-product.jpg",
        },
    )

    batch = client.post(
        "/source-refresh/batches",
        json={"limit": 5, "interval_hours": 6, "force": False},
    ).json()

    assert batch["due_available"] == 0
    assert batch["queued"] == 0
    assert batch["runner_url"] is None


def test_source_refresh_batch_can_queue_without_claiming_first_job(client) -> None:
    client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Queued-Only-Product/777",
            "title": "Queued Only Product",
            "source_price": 18.0,
            "source_shipping": 0.0,
            "description": "Queued only product",
            "image_urls": "https://images.thdstatic.com/productImages/queued-only-product.jpg",
        },
    )

    batch = client.post(
        "/source-refresh/batches",
        json={"limit": 5, "interval_hours": 6, "force": True, "auto_claim": False},
    ).json()

    assert batch["queued"] == 1
    assert batch["runner_url"] is None
    assert batch["jobs"][0]["status"] == "queued"


def test_source_refresh_batch_can_force_selected_products(client) -> None:
    selected = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Selected-Refresh-Product/888",
            "title": "Selected Refresh Product",
            "source_price": 18.0,
            "source_shipping": 0.0,
            "description": "Selected refresh product",
            "image_urls": "https://images.thdstatic.com/productImages/selected-refresh-product.jpg",
        },
    ).json()
    other = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Other-Refresh-Product/889",
            "title": "Other Refresh Product",
            "source_price": 22.0,
            "source_shipping": 0.0,
            "description": "Other refresh product",
            "image_urls": "https://images.thdstatic.com/productImages/other-refresh-product.jpg",
        },
    ).json()

    batch = client.post(
        "/source-refresh/batches",
        json={"product_ids": [selected["id"]], "limit": 5, "interval_hours": 6, "force": True, "auto_claim": False},
    ).json()

    assert batch["queued"] == 1
    assert batch["jobs"][0]["product_id"] == selected["id"]
    assert batch["jobs"][0]["product_id"] != other["id"]


def test_home_depot_capture_filters_noisy_description_and_images(client) -> None:
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/HDX-Noisy-Capture/HDR13XHFN200W-F/331012931",
            "title": "HDX Noisy Capture",
            "source_price": 17.97,
            "description": "Double-thick top provides added strength\nView More Details\nCustomer Service Center\nFresh scent controls odor",
            "image_urls": "\n".join(
                [
                    "https://images.thdstatic.com/productImages/good-front.jpg",
                    "https://contentgrid.thdstatic.com/hdus/en_US/DTCCOMNEW/fetch/ChristmasDelivery-Tools-Split-Dsk2.jpg",
                    "https://4584051c57da007007c6-68efb418da7bd7ec341101e06a5cd8ed.ssl.cf1.rackcdn.com/images/thd_dropdown_SsBnVS9.png",
                    "https://images.thdstatic.com/productImages/good-side.jpg",
                ]
            ),
        },
    ).json()

    assert [image["image_url"] for image in product["images"]] == [
        "https://images.thdstatic.com/productImages/good-front.jpg",
        "https://images.thdstatic.com/productImages/good-side.jpg",
    ]
    description = product["listing_drafts"][0]["description"]
    assert "<h3>Overview</h3>" in description
    assert "<h3>Highlights</h3>" in description
    assert "<h3>Details</h3>" in description
    assert "Double-thick top" in description
    assert "Fresh scent controls odor" in description
    assert "View More Details" not in description
    assert "Customer Service Center" not in description


def test_ebay_package_filters_legacy_noisy_home_depot_images(client, monkeypatch) -> None:
    original_filter = importer._filter_source_images
    monkeypatch.setattr(importer, "_filter_source_images", lambda source_url, image_urls: image_urls)
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/HDX-Legacy-Noisy-Capture/HDR13XHFN200W-F/331012931",
            "title": "HDX Legacy Noisy Capture",
            "source_price": 17.97,
            "description": "Legacy image filtering test",
            "image_urls": "\n".join(
                [
                    "https://images.thdstatic.com/productImages/good-front.jpg",
                    "https://contentgrid.thdstatic.com/hdus/en_US/DTCCOMNEW/fetch/ChristmasDelivery-Tools-Split-Dsk2.jpg",
                    "https://images.thdstatic.com/productImages/good-side.jpg",
                ]
            ),
        },
    ).json()
    assert len(product["images"]) == 3

    monkeypatch.setattr(importer, "_filter_source_images", original_filter)
    package = client.get(f"/products/{product['id']}/ebay-package").json()

    assert package["image_urls"] == [
        "https://images.thdstatic.com/productImages/good-front.jpg",
        "https://images.thdstatic.com/productImages/good-side.jpg",
    ]


def test_listing_readiness_reports_manual_and_api_gaps(client) -> None:
    client.patch(
        "/settings/pricing",
        json={"default_pricing_strategy": "competitor", "default_round_to_99": True},
    )
    response = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/HDX-Captured-Product/331012931",
            "title": "HDX 13 Gallon Reinforced Top Drawstring Fresh Scented Tall Kitchen Trash Bags 200 Count",
            "source_price": 17.97,
            "source_shipping": 0.0,
            "competitor_price": 21.49,
            "description": "Fresh scented bags\nDrawstring closure",
            "image_urls": (
                "data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
            ),
        },
    )
    product = response.json()

    readiness = client.get(f"/products/{product['id']}/listing-readiness").json()
    assert readiness["manual_ready"] is True
    assert readiness["api_ready"] is False
    assert readiness["missing_manual"] == []
    assert "ebay_category_id" in readiness["missing_api"]
    assert readiness["checks"]["images"] is True
    assert readiness["warnings"]

    client.patch(
        "/settings/pricing",
        json={
            "ebay_category_id": "9355",
            "ebay_merchant_location_key": "warehouse-1",
            "ebay_fulfillment_policy_id": "fulfillment-policy",
            "ebay_payment_policy_id": "payment-policy",
            "ebay_return_policy_id": "return-policy",
        },
    )
    ready = client.get(f"/products/{product['id']}/listing-readiness").json()
    assert ready["manual_ready"] is True
    assert ready["api_ready"] is True
    assert ready["missing_api"] == []

    stats = client.get("/stats/overview?range=all").json()
    readiness_mix = {item["label"]: item["value"] for item in stats["listing_readiness_mix"]}
    assert readiness_mix["API ready"] == 1
    assert readiness_mix["Manual ready"] == 0
    assert readiness_mix["Needs work"] == 0


def test_publish_ebay_sandbox_requires_write_gate(client) -> None:
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    client.patch(
        "/settings/pricing",
        json={
            "ebay_environment": "sandbox",
            "ebay_client_id": "SANDBOX-CLIENT-ID",
            "ebay_client_secret": "SANDBOX-SECRET",
            "ebay_redirect_uri": "MakSandbox-RuName",
            "ebay_access_token": "ACCESS-TOKEN",
            "ebay_category_id": "9355",
            "ebay_merchant_location_key": "warehouse-1",
            "ebay_fulfillment_policy_id": "fulfillment-policy",
            "ebay_payment_policy_id": "payment-policy",
            "ebay_return_policy_id": "return-policy",
            "ebay_enable_writes": False,
        },
    )
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Publish-Gated/111",
            "title": "Publish Gated Product",
            "source_price": 17.97,
            "source_shipping": 0.0,
            "description": "Sandbox publish gated test",
            "image_urls": tiny_png,
        },
    ).json()

    response = client.post(f"/products/{product['id']}/publish-ebay-sandbox")

    assert response.status_code == 400
    assert "writes are disabled" in response.json()["detail"]


def test_publish_ebay_sandbox_creates_inventory_offer_and_listing(client, monkeypatch) -> None:
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    client.patch(
        "/settings/pricing",
        json={
            "ebay_environment": "sandbox",
            "ebay_client_id": "SANDBOX-CLIENT-ID",
            "ebay_client_secret": "SANDBOX-SECRET",
            "ebay_redirect_uri": "MakSandbox-RuName",
            "ebay_access_token": "ACCESS-TOKEN",
            "ebay_category_id": "9355",
            "ebay_merchant_location_key": "warehouse-1",
            "ebay_fulfillment_policy_id": "fulfillment-policy",
            "ebay_payment_policy_id": "payment-policy",
            "ebay_return_policy_id": "return-policy",
            "ebay_enable_writes": True,
        },
    )
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Publish-Ready/222",
            "title": "Publish Ready Product",
            "source_price": 20.0,
            "source_shipping": 0.0,
            "description": "Sandbox publish ready test",
            "image_urls": tiny_png,
        },
    ).json()
    calls = []

    def fake_put(url, json, headers, timeout):
        calls.append({"method": "PUT", "url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(204, request=httpx.Request("PUT", url))

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"method": "POST", "url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/offer"):
            return httpx.Response(201, json={"offerId": "OFFER-123"}, request=httpx.Request("POST", url))
        return httpx.Response(200, json={"listingId": "LISTING-123"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(ebay.httpx, "put", fake_put)
    monkeypatch.setattr(ebay.httpx, "post", fake_post)

    result = client.post(f"/products/{product['id']}/publish-ebay-sandbox").json()

    assert result["environment"] == "sandbox"
    assert result["offer_id"] == "OFFER-123"
    assert result["listing_id"] == "LISTING-123"
    assert result["inventory_item_status_code"] == 204
    assert [call["method"] for call in calls] == ["PUT", "POST", "POST"]
    assert calls[0]["url"].endswith(f"/sell/inventory/v1/inventory_item/{product['sku']}")
    assert calls[1]["url"] == "https://api.sandbox.ebay.com/sell/inventory/v1/offer"
    assert calls[2]["url"] == "https://api.sandbox.ebay.com/sell/inventory/v1/offer/OFFER-123/publish"
    assert calls[0]["headers"]["Authorization"] == "Bearer ACCESS-TOKEN"
    assert calls[0]["headers"]["Content-Language"] == "en-US"
    assert calls[0]["json"]["product"]["title"] == product["listing_drafts"][0]["title"]
    assert calls[1]["json"]["categoryId"] == "9355"
    assert calls[1]["json"]["listingPolicies"]["paymentPolicyId"] == "payment-policy"

    listing = client.get("/ebay/listings").json()[0]
    assert listing["listing_id"] == "LISTING-123"
    assert listing["environment"] == "sandbox"
    assert listing["account_id"] == "sandbox"
    assert listing["status"] == "published"


def test_listing_queue_summarizes_ready_and_blocked_products(client, monkeypatch) -> None:
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    ready_product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Listing-Queue-Ready/111",
            "title": "Listing Queue Ready Product",
            "source_price": 10.0,
            "source_shipping": 0.0,
            "description": "Ready product",
            "image_urls": tiny_png,
        },
    ).json()

    monkeypatch.setattr(importer, "_download_image", lambda product_id, image_url, sort_order: None)
    blocked_product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Listing-Queue-Blocked/222",
            "title": "Listing Queue Blocked Product",
            "source_price": 12.0,
            "source_shipping": 0.0,
            "description": "Blocked product",
            "image_urls": "https://images.thdstatic.com/productImages/listing-queue-blocked.jpg",
        },
    ).json()

    queue = client.get("/listings/queue").json()

    ready_item = next(item for item in queue if item["product_id"] == ready_product["id"])
    blocked_item = next(item for item in queue if item["product_id"] == blocked_product["id"])
    assert ready_item["manual_ready"] is True
    assert ready_item["image_upload_status"] == "ready"
    assert ready_item["local_image_count"] == ready_item["image_count"] == 1
    assert ready_item["source_url"].startswith("https://www.homedepot.com/")
    assert blocked_item["manual_ready"] is False
    assert blocked_item["image_upload_status"] == "missing_downloads"
    assert blocked_item["local_image_count"] == 0
    assert "all product images downloaded" in blocked_item["missing_manual"]


def test_capture_endpoint_allows_source_page_cors(client) -> None:
    response = client.options(
        "/products/import-captured",
        headers={
            "Origin": "https://www.homedepot.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://www.homedepot.com"
    assert response.headers["access-control-allow-private-network"] == "true"


def test_data_url_images_are_downloaded_and_zipped(client) -> None:
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://example.com/p/Image-Test/321",
            "title": "Image Test Product",
            "source_price": 10,
            "description": "Image test product",
            "image_urls": tiny_png,
        },
    ).json()
    assert product["images"][0]["local_path"].endswith(".png")
    image_response = client.get(f"/{product['images'][0]['local_path']}")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"

    package = client.get(f"/products/{product['id']}/ebay-package").json()
    assert package["local_image_paths"]
    assert package["manual_image_paths"] == package["local_image_paths"]
    assert package["image_upload_status"] == "ready"

    export = client.post(f"/products/{product['id']}/export-ebay").json()
    assert export["zip_path"].endswith(".zip")
    zip_response = client.get(f"/products/{product['id']}/export-ebay.zip")
    assert zip_response.status_code == 200
    assert zip_response.headers["content-type"] == "application/zip"

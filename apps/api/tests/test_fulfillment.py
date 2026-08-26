def _prepare_order(client, *, gift_card_id: int | None = None):
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Auto-Order-Test/123456",
            "title": "Auto Order Test Product",
            "source_price": 20.0,
            "source_shipping": 0.0,
            "description": "Supplier order workflow test",
            "image_urls": "https://images.thdstatic.com/productImages/auto-order-test.jpg",
        },
    ).json()
    order = client.post("/orders/sync-sandbox").json()
    assert order["items"][0]["product_id"] == product["id"]
    payload = {
        "gift_card_id": gift_card_id,
        "recipient_name": "Test Buyer",
        "address_line1": "123 Test Street",
        "city": "Coral Springs",
        "state": "FL",
        "postal_code": "33071",
    }
    return client.post(f"/orders/{order['id']}/supplier-orders/prepare", json=payload)


def test_supplier_order_requires_shipping_address_before_approval(client) -> None:
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Auto-Order-Blocked/987654",
            "title": "Auto Order Blocked Product",
            "source_price": 18.0,
            "source_shipping": 0.0,
        },
    ).json()
    order = client.post("/orders/sync-sandbox").json()
    assert order["items"][0]["product_id"] == product["id"]

    prepared = client.post(f"/orders/{order['id']}/supplier-orders/prepare", json={}).json()

    assert prepared["status"] == "needs_review"
    assert "shipping address" in prepared["failure_reason"]
    response = client.post(f"/supplier-orders/{prepared['id']}/approve")
    assert response.status_code == 422


def test_supplier_checkout_uses_only_the_seller_notification_phone(client) -> None:
    saved = client.patch(
        "/settings/catalog",
        json={"fulfillment_notification_phone": "+1 555 010 2020"},
    )
    assert saved.status_code == 200
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Seller-Phone-Test/654321",
            "title": "Seller Phone Test Product",
            "source_price": 5.0,
            "source_shipping": 0.0,
        },
    ).json()
    order = client.post("/orders/sync-sandbox").json()
    assert order["items"][0]["product_id"] == product["id"]
    prepared = client.post(
        f"/orders/{order['id']}/supplier-orders/prepare",
        json={
            "recipient_name": "Test Buyer",
            "address_line1": "123 Test Street",
            "city": "Coral Springs",
            "state": "FL",
            "postal_code": "33071",
            "phone": "+1 555 999 9999",
        },
    ).json()
    assert prepared["phone"] == "+1 555 010 2020"


def test_supplier_order_approval_includes_configured_supplier_tax_allowance(client) -> None:
    saved = client.patch("/settings/pricing", json={"default_sales_tax_percent": 8.0})
    assert saved.status_code == 200
    prepared = _prepare_order(client).json()
    assert prepared["item_subtotal"] == 20.0
    assert prepared["sales_tax"] == 1.6
    assert prepared["total"] == 21.6
    approved = client.post(f"/supplier-orders/{prepared['id']}/approve").json()
    assert approved["approved_total"] == 21.6


def test_home_depot_tracking_capture_is_idempotent_and_feeds_ebay_upload(client) -> None:
    order = client.post("/orders/sync-sandbox").json()
    payload = {
        "supplier": "home_depot",
        "external_order_id": "WK35437792",
        "tracking_number": "C12285845379131",
        "carrier": "OnTrac",
        "order_id": order["id"],
    }
    first = client.post("/supplier-orders/tracking-capture", json=payload)
    assert first.status_code == 200
    assert first.json()["matched"] is True
    assert first.json()["created"] is True
    second = client.post("/supplier-orders/tracking-capture", json={key: value for key, value in payload.items() if key != "order_id"})
    assert second.status_code == 200
    assert second.json()["supplier_order_id"] == first.json()["supplier_order_id"]
    pending = client.get("/supplier-orders/ebay-tracking-next").json()
    assert pending["tracking_number"] == "C12285845379131"
    assert pending["carrier"] == "OnTrac"


def test_supplier_order_blocks_a_purchase_that_exceeds_ebay_revenue(client) -> None:
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Unsafe-Package-Price/246810",
            "title": "Unsafe Package Price Product",
            "source_price": 192.24,
            "source_shipping": 0.0,
        },
    ).json()
    order = client.post("/orders/sync-sandbox").json()
    assert order["items"][0]["product_id"] == product["id"]

    prepared = client.post(
        f"/orders/{order['id']}/supplier-orders/prepare",
        json={
            "recipient_name": "Test Buyer",
            "address_line1": "123 Test Street",
            "city": "Coral Springs",
            "state": "FL",
            "postal_code": "33071",
        },
    ).json()

    assert prepared["status"] == "needs_review"
    assert "supplier total $192.24 exceeds eBay order revenue" in prepared["failure_reason"]
    response = client.post(f"/supplier-orders/{prepared['id']}/approve")
    assert response.status_code == 422


def test_gift_card_supplier_order_flow_debits_card_once(client) -> None:
    card = client.post(
        "/gift-cards",
        json={
            "supplier": "home_depot",
            "label": "Test Home Depot card",
            "last_four": "1234",
            "face_value": 50.0,
            "acquisition_cost": 45.0,
            "secret_ref": "AutoZS/HomeDepot/TestCard1234",
        },
    ).json()

    prepared_response = _prepare_order(client, gift_card_id=card["id"])
    assert prepared_response.status_code == 200
    prepared = prepared_response.json()
    assert prepared["status"] == "draft"
    assert prepared["item_subtotal"] == 20.0
    assert prepared["gift_card_amount"] == 20.0
    assert prepared["card_amount"] == 0.0

    approved = client.post(f"/supplier-orders/{prepared['id']}/approve").json()
    assert approved["status"] == "queued"

    claimed = client.post("/supplier-orders/next").json()
    assert claimed["id"] == prepared["id"]
    assert claimed["status"] == "placing"

    placed = client.patch(
        f"/supplier-orders/{prepared['id']}",
        json={
            "status": "placed",
            "external_order_id": "HD-ORDER-001",
            "item_subtotal": 20.0,
            "sales_tax": 0.0,
            "shipping_cost": 0.0,
            "gift_card_amount": 20.0,
            "card_amount": 0.0,
            "total": 20.0,
        },
    ).json()
    assert placed["status"] == "placed"

    cards = client.get("/gift-cards").json()
    assert cards[0]["current_balance"] == 30.0
    client.patch(f"/supplier-orders/{prepared['id']}", json={"status": "placed"})
    cards = client.get("/gift-cards").json()
    assert cards[0]["current_balance"] == 30.0

    missing_tracking = client.patch(f"/supplier-orders/{prepared['id']}", json={"status": "shipped"})
    assert missing_tracking.status_code == 422
    assert "Carrier and tracking number" in missing_tracking.json()["detail"]

    shipped = client.patch(
        f"/supplier-orders/{prepared['id']}",
        json={"status": "shipped", "carrier": "UPS", "tracking_number": "1Z999AA10123456784"},
    )
    assert shipped.status_code == 200
    assert shipped.json()["status"] == "shipped"
    assert shipped.json()["carrier"] == "UPS"
    assert shipped.json()["tracking_number"] == "1Z999AA10123456784"

    pending = client.get("/supplier-orders/ebay-tracking-next")
    assert pending.status_code == 200
    assert pending.json()["supplier_order_id"] == prepared["id"]
    assert pending.json()["ebay_order_id"]
    assert pending.json()["account_key"]
    assert pending.json()["carrier"] == "UPS"
    assert pending.json()["tracking_number"] == "1Z999AA10123456784"


def test_checkout_credential_is_brokered_only_for_the_active_claim(client, monkeypatch) -> None:
    stored: dict[str, tuple[str, str]] = {}
    monkeypatch.setattr(
        "app.api.routes.store_generic_credential",
        lambda target, username, secret: stored.__setitem__(target, (username, secret)),
    )
    monkeypatch.setattr("app.api.routes.read_generic_credential", lambda target: stored[target])
    card = client.post(
        "/gift-cards",
        json={
            "supplier": "home_depot",
            "label": "Secure checkout card",
            "face_value": 25.0,
            "acquisition_cost": 25.0,
        },
    ).json()
    secured = client.post(
        f"/gift-cards/{card['id']}/credential",
        json={"card_number": "6035320000001234", "pin": "9876"},
    )
    assert secured.status_code == 200
    assert secured.json()["last_four"] == "1234"

    prepared = _prepare_order(client, gift_card_id=card["id"]).json()
    approved = client.post(f"/supplier-orders/{prepared['id']}/approve").json()
    assert approved["approved_total"] == 20.0
    claimed = client.post("/supplier-orders/next").json()
    assert claimed["checkout_token"]

    rejected = client.post(
        f"/supplier-orders/{prepared['id']}/checkout-credential",
        headers={"X-AutoZS-Checkout-Token": "wrong-token"},
    )
    assert rejected.status_code == 403
    credential = client.post(
        f"/supplier-orders/{prepared['id']}/checkout-credential",
        headers={"X-AutoZS-Checkout-Token": claimed["checkout_token"]},
    )
    assert credential.status_code == 200
    assert credential.headers["cache-control"] == "no-store"
    assert credential.json()["card_number"].endswith("1234")
    assert credential.json()["pin"] == "9876"


def test_home_depot_payment_card_is_secured_and_brokered_only_to_claim(client, monkeypatch) -> None:
    stored = {}
    monkeypatch.setattr(
        "app.api.routes.store_supplier_payment_credential",
        lambda supplier, **payload: stored.update({"supplier": supplier, **payload}) or payload["card_number"][-4:],
    )
    monkeypatch.setattr(
        "app.api.routes.read_supplier_payment_credential",
        lambda supplier: {
            "card_number": stored["card_number"],
            "expiration_month": stored["expiration_month"],
            "expiration_year": stored["expiration_year"],
            "security_code": stored["security_code"],
            "cardholder_name": stored["cardholder_name"],
            "billing_postal_code": stored["billing_postal_code"],
        },
    )
    secured = client.post(
        "/supplier-payment-credentials/home_depot",
        json={
            "card_number": "4111111111111111",
            "expiration_month": 8,
            "expiration_year": 2031,
            "security_code": "123",
            "cardholder_name": "Test Seller",
            "billing_postal_code": "80226",
        },
    )
    assert secured.status_code == 200
    assert secured.json() == {"supplier": "home_depot", "stored": True, "last_four": "1111"}

    prepared = _prepare_order(client).json()
    client.post(f"/supplier-orders/{prepared['id']}/approve")
    claimed = client.post("/supplier-orders/next").json()
    credential = client.post(
        f"/supplier-orders/{prepared['id']}/checkout-credential",
        headers={"X-AutoZS-Checkout-Token": claimed["checkout_token"]},
    )
    assert credential.status_code == 200
    body = credential.json()
    assert body["card_number"].endswith("1111")
    assert body["security_code"] == "123"
    assert body["cardholder_name"] == "Test Seller"
    assert body["billing_postal_code"] == "80226"
    assert credential.headers["cache-control"] == "no-store"

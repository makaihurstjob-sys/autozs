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

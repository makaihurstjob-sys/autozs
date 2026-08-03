import base64


def _captured_product(client):
    return client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/First-Real-Sale/123456789",
            "title": "First Real Sale Product",
            "source_price": 12.0,
            "source_shipping": 0.0,
            "description": "A product used to test Seller Hub order imports.",
            "image_urls": "https://images.thdstatic.com/productImages/first-sale.jpg",
        },
    ).json()


def _orders_csv() -> bytes:
    return (
        ",,,,,,,,,,,,,\n"
        "Order Number,Buyer Username,Ship To Name,Item Number,Item Title,Custom Label,Quantity,"
        "Sold For,Shipping And Handling,Total Price,Paid On Date,Ship By Date,"
        "Shipped On Date,Shipping Service,Tracking Number\n"
        "12-34567-89012,first-buyer,Jamie Rivera,800123456789,First Real Sale Product,,1,"
        "$19.53,$0.00,$19.53,Jul-27-26,Jul-29-26,,"
        "USPS Ground Advantage,\n"
        "1,record(s) downloaded,\n"
    ).encode()


def test_chrome_order_report_import_is_idempotent_and_matches_listing(client) -> None:
    product = _captured_product(client)
    marked = client.post(
        f"/products/{product['id']}/mark-listed",
        json={
            "listing_id": "800123456789",
            "account_id": "a.m.anim-59",
            "environment": "manual",
            "quantity": 1,
            "status": "active",
        },
    )
    assert marked.status_code == 200

    queued = client.post("/orders/sync?account_key=a.m.anim-59").json()
    claimed = client.post("/orders/sync/next?account_key=a.m.anim-59").json()
    assert claimed["id"] == queued["id"]
    assert claimed["status"] == "running"
    assert "autozs_report_type=orders" in claimed["runner_url"]

    payload = {
        "account_key": "a.m.anim-59",
        "run_id": claimed["id"],
        "filename": "ebay-orders-a.m.anim-59-run-1.csv",
        "report_base64": base64.b64encode(_orders_csv()).decode(),
    }
    first = client.post("/orders/import-file", json=payload)
    assert first.status_code == 200, first.text
    assert first.json() == {
        "orders_seen": 1,
        "orders_upserted": 1,
        "unmatched_items": 0,
        "run_id": claimed["id"],
    }

    orders = client.get("/orders").json()
    assert len(orders) == 1
    assert orders[0]["ebay_order_id"] == "12-34567-89012"
    assert orders[0]["buyer_username"] == "first-buyer"
    assert orders[0]["recipient_name"] == "Jamie Rivera"
    assert orders[0]["account_id"] == "a.m.anim-59"
    assert orders[0]["total"] == 19.53
    assert orders[0]["items"][0]["product_id"] == product["id"]
    assert orders[0]["items"][0]["quantity"] == 1
    assert orders[0]["items"][0]["sale_price"] == 19.53
    assert orders[0]["fulfillment_tasks"][0]["status"] == "open"
    listings = client.get("/ebay/listings").json()
    assert listings[0]["status"] == "ended"
    assert listings[0]["quantity"] == 0
    restock_jobs = client.get("/listing-jobs").json()
    assert len(restock_jobs) == 1
    assert restock_jobs[0]["product_id"] == product["id"]
    assert restock_jobs[0]["action"] == "publish"
    assert restock_jobs[0]["status"] == "queued"
    assert "automatic restock" in restock_jobs[0]["message"]

    repeated = client.post("/orders/import-file", json=payload)
    assert repeated.status_code == 200
    repeated_orders = client.get("/orders").json()
    assert len(repeated_orders) == 1
    assert len(repeated_orders[0]["items"]) == 1
    assert len(repeated_orders[0]["fulfillment_tasks"]) == 1
    assert len(client.get("/listing-jobs").json()) == 1


def test_order_report_import_rejects_reports_without_order_numbers(client) -> None:
    content = base64.b64encode(b"Item Number,Item Title\n800123456789,No order\n").decode()
    response = client.post(
        "/orders/import-file",
        json={
            "account_key": "a.m.anim-59",
            "filename": "orders.csv",
            "report_base64": content,
        },
    )
    assert response.status_code == 422
    assert "Order Number" in response.json()["detail"]

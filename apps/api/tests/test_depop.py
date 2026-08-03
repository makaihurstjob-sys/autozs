def test_depop_account_variant_and_isolated_worker_queue(client) -> None:
    account = client.post(
        "/depop/accounts",
        json={
            "key": "personal-closet",
            "label": "Personal Closet",
            "username": "closet-owner",
            "chrome_profile_root": "C:\\AutoZS\\profiles\\depop",
            "enabled": True,
            "writes_enabled": True,
        },
    )
    assert account.status_code == 200
    assert account.json()["writes_enabled"] is True

    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://owned-inventory.local/jacket-1",
            "title": "Vintage denim jacket",
            "source_price": 0,
            "source_shipping": 0,
            "source_in_stock": True,
            "description": "Owned personal clothing.",
            "image_urls": "\n".join(
                [
                    "https://images.local/jacket-front.jpg",
                    "https://images.local/jacket-back.jpg",
                    "https://images.local/jacket-label.jpg",
                ]
            ),
        },
    )
    assert product.status_code == 200
    product_body = product.json()

    variant = client.post(
        "/depop/variants",
        json={
            "product_id": product_body["id"],
            "account_key": "personal-closet",
            "variant_key": "look-a",
            "title": "Vintage denim jacket",
            "description": "Original photos of my own jacket.",
            "price": 42,
            "image_ids": [image["id"] for image in product_body["images"][:3]],
            "size": "M",
            "condition": "Good",
            "color": "Blue",
        },
    )
    assert variant.status_code == 200
    assert variant.json()["status"] == "ready"
    assert len(variant.json()["image_ids"]) == 3

    product_after = client.get("/products").json()[0]
    assert {draft["marketplace"] for draft in product_after["listing_drafts"]} >= {"ebay", "depop"}

    job = client.post("/depop/jobs", json={"variant_id": variant.json()["id"], "action": "create"})
    assert job.status_code == 200
    assert job.json()["status"] == "queued"
    assert "dedicated Depop Chrome profile" in job.json()["message"]
    assert client.get("/depop/jobs").json()[0]["variant_id"] == variant.json()["id"]

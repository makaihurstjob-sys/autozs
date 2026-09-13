def test_depop_account_variant_and_isolated_worker_queue(client, monkeypatch, tmp_path) -> None:
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
            "brand": "Other",
            "shipping_method": "Medium Under 1lb",
            "color": "Blue",
            "category": "Bags",
        },
    )
    assert variant.status_code == 200
    assert variant.json()["status"] == "ready"
    assert len(variant.json()["image_ids"]) == 3

    reassigned = client.patch(
        f"/depop/variants/{variant.json()['id']}",
        json={"account_key": "personal-closet"},
    )
    assert reassigned.status_code == 200
    assert reassigned.json()["account_key"] == "personal-closet"

    product_after = client.get("/products").json()[0]
    assert {draft["marketplace"] for draft in product_after["listing_drafts"]} >= {"ebay", "depop"}

    # The real browser consumes downloaded files, not remote source URLs.
    from app.core.database import get_db
    from app.main import app
    from app.models.domain import ProductImage
    monkeypatch.setattr("app.services.depop_jobs.PROJECT_ROOT", tmp_path)
    (tmp_path / "downloads").mkdir()
    (tmp_path / "downloads" / "image.jpg").write_bytes(b"test image")
    database = next(app.dependency_overrides[get_db]())
    for image in database.query(ProductImage).all():
        image.local_path = "downloads/image.jpg"
    database.commit()
    database.close()
    job = client.post("/depop/jobs", json={"variant_id": variant.json()["id"], "action": "create"})
    assert job.status_code == 200
    assert job.json()["status"] == "queued"
    assert "dedicated Depop Chrome profile" in job.json()["message"]
    assert client.get("/depop/jobs").json()[0]["variant_id"] == variant.json()["id"]

    single = client.get(f"/depop/jobs/{job.json()['id']}")
    assert single.status_code == 200
    assert single.json()["id"] == job.json()["id"]

    run = client.post("/depop/jobs/next")
    assert run.status_code == 200
    run_body = run.json()
    assert run_body["job"]["status"] == "running"
    assert run_body["job"]["attempts"] == 1
    assert run_body["job"]["runner_url"].startswith("https://www.depop.com/products/create/")
    assert f"autozs_job_id={job.json()['id']}" in run_body["job"]["runner_url"]
    assert run_body["package"]["variant_id"] == variant.json()["id"]
    assert run_body["package"]["title"] == "Vintage denim jacket"
    assert run_body["package"]["price"] == 42
    assert len(run_body["package"]["image_urls"]) == 3
    assert run_body["package"]["shipping_method"] == "Extra large Under 10lb"

    assert client.get("/depop/jobs?status=running").json()[0]["id"] == job.json()["id"]

    # Only one Depop runner tab exists, so a second claim attempt must not
    # steal the job that is already running.
    blocked = client.post("/depop/jobs/next")
    assert blocked.status_code == 404

    published = client.post(
        f"/depop/jobs/{job.json()['id']}/published",
        json={
            "depop_listing_id": "closet-owner-vintage-denim-ab12",
            "listing_url": "https://www.depop.com/products/closet-owner-vintage-denim-ab12/",
            "published_at": "2026-08-26T12:00:00",
        },
    )
    assert published.status_code == 200
    assert published.json()["status"] == "completed"
    assert published.json()["progress"] == 100
    assert "closet-owner-vintage-denim-ab12" in published.json()["message"]

    published_variant = client.get("/depop/variants").json()[0]
    assert published_variant["status"] == "published"
    assert published_variant["depop_listing_id"] == "closet-owner-vintage-denim-ab12"
    assert published_variant["published_at"] == "2026-08-26T12:00:00"

    completed = client.patch(
        f"/depop/variants/{variant.json()['id']}",
        json={"status": "active", "depop_listing_id": "d-123", "published_at": "2026-08-26T12:00:00"},
    )
    assert completed.status_code == 200
    assert completed.json()["depop_listing_id"] == "d-123"
    assert completed.json()["status"] == "active"


def test_depop_jobs_next_returns_404_when_queue_is_empty(client) -> None:
    assert client.post("/depop/jobs/next").status_code == 404


def test_schedule_approved_photos_creates_idempotent_four_photo_batches(client, monkeypatch, tmp_path) -> None:
    import httpx

    def fail_image_download(*args, **kwargs):
        raise httpx.ConnectError("offline test image")

    monkeypatch.setattr("app.api.routes.httpx.get", fail_image_download)
    client.post(
        "/depop/accounts",
        json={"key": "closet", "label": "Closet", "enabled": True, "writes_enabled": True},
    )
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://example.test/bag",
            "title": "Everyday shoulder bag",
            "source_price": 10,
            "source_in_stock": True,
            "image_urls": "https://images.test/cover.jpg",
        },
    ).json()
    imported = client.post(
        "/depop/amazon-import",
        json={
            "product_id": product["id"],
            "account_key": "closet",
            "price": 10,
            "title": "Everyday shoulder bag",
            "variations": [{"label": "Black", "asin": "BLACK1", "image_url": "https://images.test/black.jpg"}],
            "review_photos": [
                {"image_url": f"https://images.test/review-{index}.jpg", "review_id": f"r{index}"}
                for index in range(9)
            ],
        },
    ).json()
    variant = imported["variants"][0]
    for photo in imported["photos"]:
        if photo["kind"] != "review":
            continue
        decision = client.post(
            f"/depop/source-photos/{photo['id']}/decision",
            json={"status": "approved", "variant_id": variant["id"]},
        )
        assert decision.status_code == 200

    from app.core.database import get_db
    from app.main import app
    from app.models.domain import ProductImage
    monkeypatch.setattr("app.services.depop_jobs.PROJECT_ROOT", tmp_path)
    (tmp_path / "downloads").mkdir()
    (tmp_path / "downloads" / "image.jpg").write_bytes(b"test image")
    database = next(app.dependency_overrides[get_db]())
    for image in database.query(ProductImage).all():
        image.local_path = "downloads/image.jpg"
    database.commit()
    database.close()
    client.patch(f"/depop/variants/{variant['id']}", json={"description": "My bag", "brand": "Other", "category": "Bags", "shipping_method": "Medium Under 1lb"})

    scheduled = client.post(
        "/depop/jobs/schedule-approved",
        json={"account_key": "closet", "timezone": "America/Chicago", "daily_hours": [12, 20]},
    )
    assert scheduled.status_code == 200
    body = scheduled.json()
    assert body["listings_scheduled"] == 2
    assert body["variants_created"] == 1
    assert body["approved_photos_used"] == 8
    assert body["approved_photos_remaining"] == 1
    assert all(len(job["image_urls"]) == 4 for job in body["jobs"])
    assert all(job["brand"] == "Other" for job in body["jobs"])
    assert all(job["category"] == "Bags" for job in body["jobs"])
    assert all(job["condition"] == "Brand new" for job in body["jobs"])
    assert [job["scheduled_for"] for job in body["jobs"]] == sorted(job["scheduled_for"] for job in body["jobs"])

    repeated = client.post(
        "/depop/jobs/schedule-approved",
        json={"account_key": "closet", "timezone": "America/Chicago", "daily_hours": [12, 20]},
    ).json()
    assert repeated["listings_scheduled"] == 0
    assert len(client.get("/depop/jobs").json()) == 2


def test_photo_decision_blur_mode_preserves_full_photo_on_square_background(
    client, monkeypatch, tmp_path
) -> None:
    import io

    from PIL import Image

    source = Image.new("RGB", (400, 800), (235, 225, 215))
    for x in range(120, 280):
        for y in range(180, 620):
            source.putpixel((x, y), (20, 25, 30))
    buffer = io.BytesIO()
    source.save(buffer, "JPEG")

    class ImageResponse:
        content = buffer.getvalue()
        headers = {"content-type": "image/jpeg"}
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

    monkeypatch.setattr("app.api.routes.httpx.get", lambda *args, **kwargs: ImageResponse())
    monkeypatch.setattr("app.api.routes.PROJECT_ROOT", tmp_path)

    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://example.test/portrait-bag",
            "title": "Portrait bag photo",
            "source_price": 10,
            "source_in_stock": True,
            "image_urls": "https://images.test/cover.jpg",
        },
    ).json()
    imported = client.post(
        "/depop/amazon-import",
        json={
            "product_id": product["id"],
            "title": "Portrait bag photo",
            "variations": [
                {"label": "Black", "asin": "BLACK", "image_url": "https://images.test/black.jpg"}
            ],
            "review_photos": [
                {"image_url": "https://images.test/portrait.jpg", "review_id": "review-1"}
            ],
        },
    ).json()
    photo = next(item for item in imported["photos"] if item["kind"] == "review")
    variant = imported["variants"][0]

    decision = client.post(
        f"/depop/source-photos/{photo['id']}/decision",
        json={
            "status": "approved",
            "variant_id": variant["id"],
            "background_mode": "blur",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["background_mode"] == "blur"
    saved = tmp_path / "downloads" / "product_images" / str(product["id"]) / f"depop-{photo['id']}.jpg"
    assert saved.exists()
    with Image.open(saved) as rendered:
        assert rendered.size == (1200, 1200)
        # The full portrait foreground occupies the center rather than being
        # cropped to a square; the dark subject remains bounded on both sides.
        assert rendered.getpixel((600, 600))[0] < 80
        assert rendered.getpixel((100, 600))[0] > 100


def test_amazon_depop_import_removes_product_from_ebay_automation(client) -> None:
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.amazon.com/dp/B0PURSE123",
            "title": "COOLOME Colorful purse",
            "source_brand": "COOLOME",
            "source_price": 12,
            "source_shipping": 0,
            "source_in_stock": True,
            "description": "Supplier description",
            "image_urls": "https://images.local/purse.jpg",
        },
    ).json()
    assert product["status"] == "monitoring"

    imported = client.post(
        "/depop/amazon-import",
        json={
            "product_id": product["id"],
            "parent_asin": "B0PURSE123",
            "price": 12,
            "title": "Colorful purse",
            "variations": [
                {"label": "Red", "asin": "B0PURSE124", "image_url": "https://images.local/red.jpg"}
            ],
        },
    )
    assert imported.status_code == 200
    assert imported.json()["variants"][0]["price"] == 24
    assert imported.json()["variants"][0]["title"] == "Colorful purse - Red"
    product_after = next(item for item in client.get("/products").json() if item["id"] == product["id"])
    assert product_after["status"] == "paused"
    assert all(draft["marketplace"] != "ebay" for draft in product_after["listing_drafts"])

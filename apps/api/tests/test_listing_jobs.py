from datetime import datetime, timedelta, timezone

from PIL import Image


PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def create_ready_product(client, title: str = "Queue Ready Product", source_id: str = "123456789") -> dict:
    configure_matching_browser_account(client)
    return client.post(
        "/products/import-captured",
        json={
            "source_url": f"https://www.homedepot.com/p/Queue-Ready/{source_id}",
            "title": title,
            "source_price": 10.0,
            "source_shipping": 0.0,
            "competitor_price": 24.99,
            "description": "Captured details for queue testing",
            "image_urls": PNG_DATA_URL,
        },
    ).json()


def configure_matching_browser_account(client, username: str = "autozs-seller") -> None:
    client.patch("/settings/pricing", json={"ebay_expected_username": username})
    client.post(
        "/ebay/browser-account",
        json={
            "detected_username": username,
            "url": "https://www.ebay.com/sh/overview",
            "marketplace": "EBAY_US",
            "source": "test",
        },
    )


def test_listing_jobs_enqueue_run_and_mark_saved(client) -> None:
    product = create_ready_product(client)

    created = client.post(
        "/listing-jobs",
        json={"product_ids": [product["id"]], "ebay_account_key": "manual"},
    )

    assert created.status_code == 200
    jobs = created.json()
    assert len(jobs) == 1
    assert jobs[0]["product_id"] == product["id"]
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["manual_ready"] is True
    assert jobs[0]["assistant_url"].startswith("https://www.ebay.com/sl/prelist/home?")

    duplicate = client.post(
        "/listing-jobs",
        json={"product_ids": [product["id"]], "ebay_account_key": "manual"},
    ).json()
    assert duplicate[0]["id"] == jobs[0]["id"]
    assert len(client.get("/listing-jobs").json()) == 1

    run = client.post(f"/listing-jobs/{jobs[0]['id']}/run").json()
    assert run["job"]["status"] == "running"
    assert run["job"]["attempts"] == 1
    assert run["package"]["product_id"] == product["id"]
    assert run["package"]["manual_image_paths"]
    assert f"autozs_job_id={jobs[0]['id']}" in run["job"]["assistant_url"]

    ready = client.patch(
        f"/listing-jobs/{jobs[0]['id']}",
        json={"status": "ready_to_save", "message": "Filled and uploaded; ready for manual save"},
    ).json()
    assert ready["status"] == "ready_to_save"
    assert ready["message"] == "Filled and uploaded; ready for manual save"

    saved = client.patch(
        f"/listing-jobs/{jobs[0]['id']}",
        json={"status": "saved_draft", "ebay_draft_id": "5095967377601", "message": "Saved for later on eBay"},
    ).json()
    assert saved["status"] == "saved_draft"
    assert saved["ebay_draft_id"] == "5095967377601"
    assert saved["message"] == "Saved for later on eBay"


def test_existing_draft_assistant_url_reopens_that_draft(client) -> None:
    product = create_ready_product(client, "Existing Draft Reschedule")
    job = client.post("/listing-jobs", json={"product_ids": [product["id"]]}).json()[0]

    updated = client.patch(
        f"/listing-jobs/{job['id']}",
        json={"status": "queued", "ebay_draft_id": "5123456789001"},
    ).json()

    assert updated["assistant_url"].startswith(
        "https://www.ebay.com/lstng?draftId=5123456789001&mode=AddItem&"
    )
    assert "autozs_fill=1" in updated["assistant_url"]
    assert f"autozs_job_id={job['id']}" in updated["assistant_url"]


def test_listing_job_rejects_draft_id_owned_by_another_product(client) -> None:
    first_product = create_ready_product(client, "First Draft Owner", "draft-owner-1")
    second_product = create_ready_product(client, "Second Draft Owner", "draft-owner-2")
    first_job = client.post("/listing-jobs", json={"product_ids": [first_product["id"]]}).json()[0]
    second_job = client.post("/listing-jobs", json={"product_ids": [second_product["id"]]}).json()[0]
    draft_id = "5313646448913"

    first_saved = client.patch(
        f"/listing-jobs/{first_job['id']}",
        json={"status": "saved_draft", "ebay_draft_id": draft_id},
    ).json()
    assert first_saved["ebay_draft_id"] == draft_id

    collision = client.patch(
        f"/listing-jobs/{second_job['id']}",
        json={"status": "ready_to_save", "ebay_draft_id": draft_id},
    ).json()

    assert collision["status"] == "needs_review"
    assert collision["ebay_draft_id"] is None
    assert f"product {first_product['id']}" in collision["message"]
    assert collision["assistant_url"].startswith("https://www.ebay.com/sl/prelist/home?")


def test_draft_verification_rejects_another_products_draft_id(client) -> None:
    first_product = create_ready_product(client, "Verified Draft Owner", "draft-verify-owner-1")
    second_product = create_ready_product(client, "Wrong Draft Verification", "draft-verify-owner-2")
    first_job = client.post("/listing-jobs", json={"product_ids": [first_product["id"]]}).json()[0]
    second_job = client.post("/listing-jobs", json={"product_ids": [second_product["id"]]}).json()[0]
    draft_id = "5264142176412"
    client.patch(
        f"/listing-jobs/{first_job['id']}",
        json={"status": "saved_draft", "ebay_draft_id": draft_id},
    )

    collision = client.post(
        f"/listing-jobs/{second_job['id']}/verify-draft",
        json={"exists": True, "ebay_draft_id": draft_id, "url": f"https://www.ebay.com/lstng?draftId={draft_id}"},
    ).json()

    assert collision["status"] == "needs_review"
    assert collision["ebay_draft_id"] is None
    assert f"product {first_product['id']}" in collision["message"]


def test_listing_job_draft_verification_tombstones_missing_draft_and_allows_reimport(client) -> None:
    product = create_ready_product(client, "Deleted eBay Draft Product")
    job = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "ebay_account_key": "manual",
            "listing_schedule_at": "2026-07-25T19:00:00",
        },
    ).json()[0]
    saved = client.patch(
        f"/listing-jobs/{job['id']}",
        json={"status": "saved_draft", "ebay_draft_id": "5121504565001", "message": "Saved for later on eBay"},
    ).json()
    assert saved["status"] == "saved_draft"
    client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "800241899128", "account_id": "manual", "status": "scheduled"},
    )

    tombstoned = client.post(
        f"/listing-jobs/{job['id']}/verify-draft",
        json={
            "exists": False,
            "ebay_draft_id": "5121504565001",
            "url": "https://www.ebay.com/lstng?draftId=5121504565001&mode=AddItem",
            "message": "eBay reported the draft no longer exists.",
        },
    ).json()

    assert tombstoned["status"] == "tombstoned"
    assert tombstoned["ebay_draft_id"] == "5121504565001"
    assert "no longer exists" in tombstoned["message"]
    listing = next(item for item in client.get("/ebay/listings").json() if item["product_id"] == product["id"])
    assert listing["status"] == "tombstoned"
    saved_product = next(item for item in client.get("/products").json() if item["id"] == product["id"])
    assert saved_product["listing_schedule_at"] is None

    reimport = client.post("/listing-jobs", json={"product_ids": [product["id"]], "ebay_account_key": "manual"}).json()[0]
    assert reimport["id"] != job["id"]
    assert reimport["status"] == "queued"


def test_manual_tombstone_clears_listing_and_product_schedule(client) -> None:
    product = create_ready_product(client, "Manually Deleted Scheduled Draft")
    job = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "ebay_account_key": "manual",
            "listing_schedule_at": "2026-07-24T19:00:00",
        },
    ).json()[0]
    client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "800241899129", "account_id": "manual", "status": "scheduled"},
    )

    tombstoned = client.patch(
        f"/listing-jobs/{job['id']}",
        json={"status": "tombstoned", "message": "Deleted from eBay Listings bulk action"},
    ).json()

    assert tombstoned["status"] == "tombstoned"
    assert tombstoned["listing_schedule_at"] is None
    listing = next(item for item in client.get("/ebay/listings").json() if item["product_id"] == product["id"])
    assert listing["status"] == "tombstoned"
    saved_product = next(item for item in client.get("/products").json() if item["id"] == product["id"])
    assert saved_product["listing_schedule_at"] is None


def test_listing_jobs_next_only_starts_due_jobs(client) -> None:
    product = create_ready_product(client, "Scheduled Queue Product")
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    job = client.post(
        "/listing-jobs",
        json={"product_ids": [product["id"]], "scheduled_for": future},
    ).json()[0]

    not_due = client.post("/listing-jobs/next")
    assert not_due.status_code == 404
    assert "No queued listing jobs are due" in not_due.json()["detail"]

    client.patch(
        f"/listing-jobs/{job['id']}",
        json={"status": "queued", "scheduled_for": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()},
    )
    due = client.post("/listing-jobs/next").json()

    assert due["job"]["id"] == job["id"]
    assert due["job"]["status"] == "running"
    assert due["package"]["sku"] == product["sku"]


def test_listing_job_needs_review_when_product_is_not_ready(client) -> None:
    configure_matching_browser_account(client)
    product = client.post(
        "/products/import",
        json={"urls": "https://www.homedepot.com/p/Queue-Missing/987654321"},
    ).json()["products"][0]
    job = client.post("/listing-jobs", json={"product_ids": [product["id"]]}).json()[0]

    run = client.post(f"/listing-jobs/{job['id']}/run").json()

    assert run["job"]["status"] == "needs_review"
    assert run["package"] is None
    assert "Needs review" in run["job"]["message"]
    assert run["job"]["missing_manual"]


def test_listing_job_blocks_when_browser_account_mismatches(client) -> None:
    product = create_ready_product(client, "Wrong Browser Account Product")
    client.post(
        "/ebay/browser-account",
        json={
            "detected_username": "wrong-seller",
            "url": "https://www.ebay.com/sh/overview",
            "marketplace": "EBAY_US",
            "source": "test",
        },
    )
    job = client.post("/listing-jobs", json={"product_ids": [product["id"]]}).json()[0]

    run = client.post(f"/listing-jobs/{job['id']}/run").json()

    assert run["job"]["status"] == "needs_review"
    assert run["package"] is None
    assert "Chrome is signed in as wrong-seller, expected autozs-seller" in run["job"]["message"]


def test_browser_account_ignores_ebay_footer_user_agreement(client) -> None:
    configure_matching_browser_account(client, username="a.m.anim-59")

    status = client.post(
        "/ebay/browser-account",
        json={
            "detected_username": "Agreement",
            "url": "https://www.ebay.com/sl/prelist/home",
            "marketplace": "EBAY_US",
            "source": "test",
        },
    ).json()

    assert status["detected_username"] == "a.m.anim-59"
    assert status["can_list"] is True


def test_browser_account_ignores_listing_weight_unit_as_username(client) -> None:
    configure_matching_browser_account(client, username="a.m.anim-59")

    status = client.post(
        "/ebay/browser-account",
        json={
            "detected_username": "kg",
            "url": "https://www.ebay.com/lstng?draftId=123&mode=AddItem",
            "marketplace": "EBAY_US",
            "source": "chrome-extension",
        },
    ).json()

    assert status["detected_username"] == "a.m.anim-59"
    assert status["can_list"] is True


def test_browser_account_preserves_match_on_listing_page_false_positive(client) -> None:
    configure_matching_browser_account(client, username="a.m.anim-59")

    status = client.post(
        "/ebay/browser-account",
        json={
            "detected_username": "Nickel",
            "url": "https://www.ebay.com/lstng?draftId=123&mode=AddItem",
            "marketplace": "EBAY_US",
            "source": "chrome-extension",
        },
    ).json()

    assert status["detected_username"] == "a.m.anim-59"
    assert status["can_list"] is True


def test_named_account_profile_expected_username_is_enforced(client) -> None:
    product = create_ready_product(client, "Named Account Product")
    account = client.post(
        "/ebay/accounts",
        json={"label": "Real Store", "account_id": "real-store", "environment": "production"},
    ).json()
    client.post(
        "/ebay/browser-account",
        json={
            "detected_username": "real-store",
            "url": "https://www.ebay.com/sh/overview",
            "marketplace": "EBAY_US",
            "source": "test",
            "account_key": account["key"],
        },
    )
    job = client.post("/listing-jobs", json={"product_ids": [product["id"]], "ebay_account_key": account["key"]}).json()[0]

    run = client.post(f"/listing-jobs/{job['id']}/run").json()

    assert run["job"]["status"] == "running"
    assert run["package"]["product_id"] == product["id"]
    assert f"autozs_account_key={account['key']}" in run["job"]["assistant_url"]


def test_prepare_images_creates_ebay_ready_square_uploads(client) -> None:
    product = create_ready_product(client, "Image Prep Product")
    client.post(f"/products/{product['id']}/download-images")

    prepared = client.post(f"/products/{product['id']}/prepare-images").json()

    assert prepared["attempted"] >= 1
    assert prepared["prepared"] >= 1
    assert prepared["size"] == 1000
    edited_paths = [image["local_path"] for image in prepared["images"] if image["local_path"]]
    assert any("/edited/" in path for path in edited_paths)
    with Image.open(edited_paths[0]) as image:
        assert image.size == (1000, 1000)

    package = client.get(f"/products/{product['id']}/ebay-package").json()
    assert package["manual_image_paths"]
    assert all("/edited/" in path for path in package["manual_image_paths"])


def test_listing_defaults_schedule_jobs_and_disable_offers(client) -> None:
    product = create_ready_product(client, "Scheduled Defaults Product")
    client.patch(
        "/settings/pricing",
        json={
            "default_offers_enabled": False,
            "default_listing_schedule_mode": "scheduled",
            "default_listing_schedule_days_ahead": 2,
            "default_listing_schedule_time": "10:30",
        },
    )

    package = client.get(f"/products/{product['id']}/ebay-package").json()
    assert package["offers_enabled"] is False
    assert package["listing_schedule_mode"] == "scheduled"
    assert package["listing_schedule_at"]
    assert "T10:30:00" in package["listing_schedule_at"]

    job = client.post("/listing-jobs", json={"product_ids": [product["id"]]}).json()[0]
    assert job["scheduled_for"] is None
    assert job["listing_schedule_at"]
    assert "T10:30:00" in job["listing_schedule_at"]


def test_listing_job_uses_selected_ebay_schedule_time(client) -> None:
    product = create_ready_product(client, "Explicit Schedule Product")
    schedule_at = "2026-07-01T08:00:00"

    job = client.post(
        "/listing-jobs",
        json={"product_ids": [product["id"]], "listing_schedule_at": schedule_at},
    ).json()[0]

    assert job["scheduled_for"] is None
    assert job["listing_schedule_at"] == schedule_at
    assert "autozs_listing_schedule_at=2026-07-01T08%3A00%3A00" in job["assistant_url"]

    run = client.post(f"/listing-jobs/{job['id']}/run").json()

    assert run["job"]["status"] == "running"
    assert run["package"]["listing_schedule_mode"] == "scheduled"
    assert run["package"]["listing_schedule_at"] == schedule_at


def test_rescheduling_listing_job_requeues_it_and_updates_product_calendar(client) -> None:
    product = create_ready_product(client, "Past Due Scheduled Product")
    past_schedule = "2026-07-14T19:00:00"
    future_schedule = "2026-07-20T19:45:00"

    job = client.post(
        "/listing-jobs",
        json={"product_ids": [product["id"]], "action": "publish", "listing_schedule_at": past_schedule},
    ).json()[0]
    client.post(f"/listing-jobs/{job['id']}/run").raise_for_status()

    rescheduled = client.patch(
        f"/listing-jobs/{job['id']}",
        json={
            "status": "queued",
            "scheduled_for": "2026-07-18T04:30:00",
            "listing_schedule_at": future_schedule,
            "message": "Queued on the Windows worker for rescheduling",
        },
    )

    assert rescheduled.status_code == 200
    assert rescheduled.json()["status"] == "queued"
    assert rescheduled.json()["listing_schedule_at"] == future_schedule
    saved_product = next(item for item in client.get("/products").json() if item["id"] == product["id"])
    assert saved_product["listing_schedule_at"] == future_schedule


def test_stale_running_listing_job_moves_to_needs_review(client) -> None:
    from app.core.database import get_db
    from app.main import app
    from app.models.domain import ListingJob
    from app.services.listing_jobs import flag_stale_listing_jobs

    product = create_ready_product(client, "Abandoned Worker Product")
    job = client.post(
        "/listing-jobs",
        json={"product_ids": [product["id"]], "action": "publish", "listing_schedule_at": "2026-07-20T19:45:00"},
    ).json()[0]
    client.post(f"/listing-jobs/{job['id']}/run").raise_for_status()

    session_provider = app.dependency_overrides[get_db]
    session_generator = session_provider()
    db = next(session_generator)
    try:
        record = db.get(ListingJob, job["id"])
        record.updated_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        db.commit()

        assert flag_stale_listing_jobs(db) == 1
        db.refresh(record)
        assert record.status == "needs_review"
        assert "stopped reporting" in record.message
    finally:
        session_generator.close()


def test_publish_listing_job_enables_guarded_auto_submit(client) -> None:
    product = create_ready_product(client, "Automatic Scheduled Product")
    schedule_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)).replace(
        microsecond=0
    ).isoformat()

    job = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "action": "publish",
            "listing_schedule_at": schedule_at,
        },
    ).json()[0]

    assert job["action"] == "publish"
    assert "autozs_autosubmit=1" in job["assistant_url"]
    assert f"autozs_listing_schedule_at={schedule_at.replace(':', '%3A')}" in job["assistant_url"]

    completed = client.patch(
        f"/listing-jobs/{job['id']}",
        json={
            "status": "completed",
            "listing_id": "800241899128",
            "message": "Scheduled on eBay as item 800241899128.",
        },
    ).json()

    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None
    listing = client.get("/ebay/listings").json()[0]
    assert listing["listing_id"] == "800241899128"
    assert listing["status"] == "scheduled"
    assert listing["renews_at"] is None


def test_completed_past_publish_job_creates_active_listing_with_renewal(client) -> None:
    product = create_ready_product(client, "Live Scheduled Product", "987654321")
    schedule_at = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()

    job = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "action": "publish",
            "listing_schedule_at": schedule_at,
        },
    ).json()[0]

    client.patch(
        f"/listing-jobs/{job['id']}",
        json={
            "status": "completed",
            "listing_id": "800262913581",
            "message": "Scheduled on eBay as item 800262913581.",
        },
    )

    listing = client.get("/ebay/listings").json()[0]
    assert listing["listing_id"] == "800262913581"
    assert listing["status"] == "active"
    assert listing["started_at"] is not None
    assert listing["renews_at"] is not None
    assert listing["days_until_relist"] is not None


def test_generic_live_confirmation_does_not_override_future_planned_schedule(client) -> None:
    product = create_ready_product(client, "Future Scheduled Product", "987654322")
    schedule_at = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()
    job = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "action": "publish",
            "listing_schedule_at": schedule_at,
        },
    ).json()[0]

    client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "800262913582", "account_id": "manual", "status": "active"},
    )
    client.patch(
        f"/listing-jobs/{job['id']}",
        json={
            "status": "completed",
            "listing_id": "800262913582",
            "message": "Listed on eBay as item 800262913582.",
        },
    )
    incorrectly_live = client.get("/ebay/listings").json()[0]
    assert incorrectly_live["status"] == "active"
    assert incorrectly_live["renews_at"] is not None

    client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "800262913582", "account_id": "manual", "status": "scheduled"},
    )
    client.patch(
        f"/listing-jobs/{job['id']}",
        json={
            "status": "completed",
            "listing_id": "800262913582",
            "message": "Scheduled on eBay as item 800262913582.",
        },
    )

    listing = client.get("/ebay/listings").json()[0]
    assert listing["listing_id"] == "800262913582"
    assert listing["status"] == "scheduled"
    assert listing["started_at"] is None
    assert listing["renews_at"] is None


def test_product_listing_schedule_can_be_saved_and_cleared(client) -> None:
    product = create_ready_product(client, "Per Product Listing Schedule")
    schedule_at = "2026-07-01T08:00:00"

    saved = client.patch(
        f"/products/{product['id']}/listing-schedule",
        json={"listing_schedule_at": schedule_at},
    )

    assert saved.status_code == 200
    assert saved.json()["listing_schedule_at"] == schedule_at
    assert client.get("/products").json()[0]["listing_schedule_at"] == schedule_at

    cleared = client.patch(
        f"/products/{product['id']}/listing-schedule",
        json={"listing_schedule_at": None},
    )

    assert cleared.status_code == 200
    assert cleared.json()["listing_schedule_at"] is None


def test_bulk_listing_jobs_inherit_each_product_schedule(client) -> None:
    first = create_ready_product(client, "Friday Scheduled Product", "111111111")
    second = create_ready_product(client, "Saturday Scheduled Product", "222222222")
    friday = "2026-06-26T14:00:00"
    saturday = "2026-06-27T14:00:00"

    client.patch(
        f"/products/{first['id']}/listing-schedule",
        json={"listing_schedule_at": friday},
    ).raise_for_status()
    client.patch(
        f"/products/{second['id']}/listing-schedule",
        json={"listing_schedule_at": saturday},
    ).raise_for_status()

    jobs = client.post(
        "/listing-jobs",
        json={"product_ids": [first["id"], second["id"]], "ebay_account_key": "manual"},
    ).json()
    schedules = {job["product_id"]: job["listing_schedule_at"] for job in jobs}

    assert schedules[first["id"]].startswith(friday)
    assert schedules[second["id"]].startswith(saturday)

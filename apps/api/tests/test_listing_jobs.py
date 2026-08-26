from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image


PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def create_ready_product(
    client,
    title: str = "Queue Ready Product",
    source_id: str = "123456789",
    source_price: float = 10.0,
    competitor_price: float = 24.99,
) -> dict:
    configure_matching_browser_account(client)
    return client.post(
        "/products/import-captured",
        json={
            "source_url": f"https://www.homedepot.com/p/Queue-Ready/{source_id}",
            "title": title,
            "source_price": source_price,
            "source_shipping": 0.0,
            "competitor_price": competitor_price,
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


def test_listing_jobs_next_rolls_expired_publish_schedule_forward(client) -> None:
    configure_matching_browser_account(client)
    product = create_ready_product(client, "Expired eBay Schedule Product")
    job = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "ebay_account_key": "a.m.anim-59",
            "action": "publish",
            "listing_schedule_at": "2020-01-01T19:00:00",
        },
    ).json()[0]

    started = client.post("/listing-jobs/next?ebay_account_key=a.m.anim-59").json()
    rolled = datetime.fromisoformat(started["job"]["listing_schedule_at"])
    eastern_now = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

    assert started["job"]["id"] == job["id"]
    assert started["job"]["status"] == "running"
    assert rolled >= eastern_now + timedelta(minutes=44)
    assert started["package"]["listing_schedule_at"] == started["job"]["listing_schedule_at"]
    saved_product = next(item for item in client.get("/products").json() if item["id"] == product["id"])
    assert saved_product["listing_schedule_at"] == started["job"]["listing_schedule_at"]


def test_listing_jobs_next_refuses_a_second_concurrent_runner(client) -> None:
    configure_matching_browser_account(client)
    first = create_ready_product(client, "Concurrent Runner One", source_id="770000001")
    second = create_ready_product(client, "Concurrent Runner Two", source_id="770000002")
    created = client.post(
        "/listing-jobs", json={"product_ids": [first["id"], second["id"]]}
    ).json()
    due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    for job in created:
        client.patch(f"/listing-jobs/{job['id']}", json={"status": "queued", "scheduled_for": due})

    started = client.post("/listing-jobs/next").json()
    assert started["job"]["status"] == "running"

    # Two runner tabs share one workflow key in the browser and corrupt each
    # other's drafts, so the queue must stay single-flight even though both
    # remaining jobs are due.
    blocked = client.post("/listing-jobs/next")
    assert blocked.status_code == 404

    client.patch(f"/listing-jobs/{started['job']['id']}", json={"status": "completed"})
    resumed = client.post("/listing-jobs/next").json()
    assert resumed["job"]["status"] == "running"
    assert resumed["job"]["id"] != started["job"]["id"]


def test_unpriced_product_is_rejected_before_entering_listing_queue(client) -> None:
    configure_matching_browser_account(client)
    product = client.post(
        "/products/import",
        json={"urls": "https://www.homedepot.com/p/Queue-Missing/987654321"},
    ).json()["products"][0]
    response = client.post("/listing-jobs", json={"product_ids": [product["id"]]})

    assert response.status_code == 404
    assert response.json()["detail"] == "No matching products found"


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


def test_browser_account_preserves_seller_identity_on_tracking_page_buyer_name(client) -> None:
    configure_matching_browser_account(client, username="a.m.anim-59")

    status = client.post(
        "/ebay/browser-account",
        json={
            "detected_username": "concat",
            "url": "https://www.ebay.com/ship/trk/tracking-details?itemid=800367161756",
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


def test_completed_job_reuses_listing_when_browser_account_label_changes(client) -> None:
    product = create_ready_product(client, "Account Label Reconciliation", "987654323")
    schedule_at = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()
    job = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "ebay_account_key": "a.m.anim-59",
            "action": "publish",
            "listing_schedule_at": schedule_at,
        },
    ).json()[0]

    client.post(
        f"/products/{product['id']}/mark-listed",
        json={"listing_id": "800262913583", "account_id": "manual", "status": "scheduled"},
    )
    client.patch(
        f"/listing-jobs/{job['id']}",
        json={
            "status": "completed",
            "listing_id": "800262913583",
            "message": "Scheduled on eBay as item 800262913583.",
        },
    )

    listings = client.get("/ebay/listings").json()
    assert len(listings) == 1
    assert listings[0]["listing_id"] == "800262913583"
    assert listings[0]["account_id"] == "a.m.anim-59"


def test_completed_job_quarantines_duplicate_confirmation_and_preserves_production_schedule(client) -> None:
    product = create_ready_product(client, "Duplicate Confirmation Reconciliation", "987654324")
    schedule_at = (
        datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")) + timedelta(days=3)
    ).replace(tzinfo=None, microsecond=0).isoformat()
    job = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "ebay_account_key": "a.m.anim-59",
            "action": "publish",
            "listing_schedule_at": schedule_at,
        },
    ).json()[0]

    client.post(
        f"/products/{product['id']}/mark-listed",
        json={
            "listing_id": "800262913584",
            "account_id": "a.m.anim-59",
            "environment": "production",
            "status": "scheduled",
        },
    )
    # Reproduce the legacy duplicate row using a different account label, which
    # bypasses the account/listing unique key just as the old browser race did.
    duplicate_product = create_ready_product(client, "Duplicate Confirmation Shadow", "987654325")
    client.post(
        f"/products/{duplicate_product['id']}/mark-listed",
        json={
            "listing_id": "800262913584",
            "account_id": "manual",
            "environment": "manual",
            "status": "active",
        },
    )

    client.patch(
        f"/listing-jobs/{job['id']}",
        json={
            "status": "completed",
            "listing_id": "800262913584",
            "message": "Scheduled on eBay as item 800262913584.",
        },
    )

    matches = [item for item in client.get("/ebay/listings").json() if item["listing_id"] == "800262913584"]
    sellable = [item for item in matches if item["status"] != "tombstoned"]
    assert len(sellable) == 1
    assert sellable[0]["environment"] == "production"
    assert sellable[0]["status"] == "scheduled"
    duplicate = next(item for item in matches if item["status"] == "tombstoned")
    assert duplicate["quantity"] == 0
    assert duplicate["removal_reason"] == "duplicate_local_record"


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


def test_unavailable_supplier_cannot_be_enqueued_for_listing(client) -> None:
    product = create_ready_product(client, "Unavailable Delivery Product")
    client.patch(
        f"/products/{product['id']}/capture",
        json={"source_price": 12.0, "source_in_stock": False},
    ).raise_for_status()

    response = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "ebay_account_key": "a.m.anim-59",
            "action": "publish",
            "listing_schedule_at": "2026-08-02T19:00:00Z",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "No matching products found"


def test_supplier_without_a_usable_price_cannot_be_enqueued_for_listing(client) -> None:
    product = create_ready_product(client, "Price Unavailable Product", "price-unavailable")
    client.patch(
        f"/products/{product['id']}/capture",
        json={"source_price": None, "source_price_unavailable": True, "source_in_stock": True},
    ).raise_for_status()

    response = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "ebay_account_key": "a.m.anim-59",
            "action": "publish",
            "listing_schedule_at": "2026-08-02T19:00:00Z",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "No matching products found"


def test_zero_view_rotation_publishes_replacement_before_retiring_old_listing(client) -> None:
    old_product = create_ready_product(client, "Old Zero View Faucet", "rotation-old")
    replacement = create_ready_product(client, "Replacement Faucet Connector", "rotation-new")
    client.post(
        f"/products/{replacement['id']}/supplier",
        json={
            "supplier": "home_depot",
            "source_url": "https://www.homedepot.com/p/Queue-Ready/rotation-new",
            "last_price": 10.0,
            "last_shipping": 0.0,
            "in_stock": True,
        },
    ).raise_for_status()
    client.post(
        f"/products/{old_product['id']}/mark-listed",
        json={"listing_id": "890000000001", "account_id": "a.m.anim-59", "status": "active"},
    ).raise_for_status()
    client.post(
        "/ebay/sync-runs/listing-report",
        json={
            "account_key": "a.m.anim-59",
            "source": "rotation_test",
            "tombstone_missing": False,
            "rows": [{
                "listing_id": "890000000001",
                "sku": old_product["sku"],
                "title": old_product["title"],
                "price": "24.99",
                "quantity": "1",
                "status": "Active",
                "views": "0",
                "started_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
            }],
        },
    ).raise_for_status()
    client.patch(
        "/settings/pricing",
        json={"auto_delist_zero_view_enabled": True, "auto_delist_zero_view_days": 29},
    ).raise_for_status()
    client.post(f"/products/{replacement['id']}/draft-price", json={"mode": "competitor"}).raise_for_status()
    readiness = client.get(f"/products/{replacement['id']}/listing-readiness").json()
    package = client.get(f"/products/{replacement['id']}/ebay-package").json()
    assert readiness["manual_ready"] is True, readiness
    assert package["meets_minimum_profit"] is True, package

    queued = client.post(
        "/listing-rotations/auto-queue?ebay_account_key=a.m.anim-59&limit=1"
    )
    assert queued.status_code == 200
    payload = queued.json()
    assert payload["eligible"] == 1
    assert payload["queued"] == 1
    assert payload["pairs"][0]["replacement_product_id"] == replacement["id"]
    assert not [job for job in client.get("/ebay/revision-jobs").json() if job["action"] == "retire_zero_view"]

    job_id = payload["pairs"][0]["job_id"]
    client.patch(
        f"/listing-jobs/{job_id}",
        json={
            "status": "completed",
            "listing_id": "890000000002",
            "message": "Replacement is live on eBay.",
        },
    ).raise_for_status()

    # Completion only proves eBay accepted a scheduled item. The old listing
    # remains live until the active-listings report proves the replacement is live.
    assert not [job for job in client.get("/ebay/revision-jobs").json() if job["action"] == "retire_zero_view"]
    client.post(
        "/ebay/sync-runs/listing-report",
        json={
            "account_key": "a.m.anim-59",
            "source": "rotation_test",
            "tombstone_missing": False,
            "rows": [{
                "listing_id": "890000000002",
                "sku": replacement["sku"],
                "quantity": "1",
                "status": "Active",
                "views": "0",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }],
        },
    ).raise_for_status()
    client.post("/listing-rotations/auto-queue?ebay_account_key=a.m.anim-59&limit=1").raise_for_status()

    revisions = [job for job in client.get("/ebay/revision-jobs").json() if job["action"] == "retire_zero_view"]
    assert len(revisions) == 1
    assert revisions[0]["action"] == "retire_zero_view"
    assert revisions[0]["status"] == "queued"
    before = next(item for item in client.get("/ebay/listings").json() if item["listing_id"] == "890000000001")
    assert before["quantity"] == 1
    assert before["relist_blocked"] is False

    client.patch(
        f"/ebay/revision-jobs/{revisions[0]['id']}",
        json={"status": "completed", "message": "Quantity zero confirmed by eBay."},
    ).raise_for_status()
    retired = next(item for item in client.get("/ebay/listings").json() if item["listing_id"] == "890000000001")
    assert retired["quantity"] == 0
    assert retired["relist_blocked"] is True
    assert retired["removal_reason"] == "zero_views_29_days"


def test_zero_view_rotation_survives_a_relist_that_resets_started_at(client) -> None:
    # Regression: started_at is overwritten on every relist/resync, so age-based
    # pruning must anchor on first_listed_at instead or a long-dead listing that
    # happens to get relisted dodges rotation forever.
    old_product = create_ready_product(client, "Old Zero View Sprayer", "rotation-relist-old")
    replacement = create_ready_product(client, "Replacement Sprayer Head", "rotation-relist-new")
    client.post(
        f"/products/{replacement['id']}/supplier",
        json={
            "supplier": "home_depot",
            "source_url": "https://www.homedepot.com/p/Queue-Ready/rotation-relist-new",
            "last_price": 10.0,
            "last_shipping": 0.0,
            "in_stock": True,
        },
    ).raise_for_status()
    client.post(
        f"/products/{old_product['id']}/mark-listed",
        json={"listing_id": "890000000101", "account_id": "a.m.anim-59", "status": "active"},
    ).raise_for_status()

    # First sync: the listing genuinely started 60 days ago.
    client.post(
        "/ebay/sync-runs/listing-report",
        json={
            "account_key": "a.m.anim-59",
            "source": "rotation_test",
            "tombstone_missing": False,
            "rows": [{
                "listing_id": "890000000101",
                "sku": old_product["sku"],
                "title": old_product["title"],
                "price": "24.99",
                "quantity": "1",
                "status": "Active",
                "views": "0",
                "started_at": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
            }],
        },
    ).raise_for_status()
    before_relist = next(item for item in client.get("/ebay/listings").json() if item["listing_id"] == "890000000101")
    assert before_relist["first_listed_at"] is not None

    # Second sync: eBay reports a relist, resetting started_at to 5 days ago.
    # first_listed_at must stay pinned to the original 60-day-old date.
    client.post(
        "/ebay/sync-runs/listing-report",
        json={
            "account_key": "a.m.anim-59",
            "source": "rotation_test",
            "tombstone_missing": False,
            "rows": [{
                "listing_id": "890000000101",
                "sku": old_product["sku"],
                "title": old_product["title"],
                "price": "24.99",
                "quantity": "1",
                "status": "Active",
                "views": "0",
                "started_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
            }],
        },
    ).raise_for_status()
    after_relist = next(item for item in client.get("/ebay/listings").json() if item["listing_id"] == "890000000101")
    assert after_relist["started_at"] != before_relist["started_at"]
    assert after_relist["first_listed_at"] == before_relist["first_listed_at"]

    client.patch(
        "/settings/pricing",
        json={"auto_delist_zero_view_enabled": True, "auto_delist_zero_view_days": 29},
    ).raise_for_status()
    client.post(f"/products/{replacement['id']}/draft-price", json={"mode": "competitor"}).raise_for_status()

    queued = client.post("/listing-rotations/auto-queue?ebay_account_key=a.m.anim-59&limit=1")
    assert queued.status_code == 200
    payload = queued.json()
    assert payload["eligible"] == 1, payload
    assert payload["queued"] == 1
    assert payload["pairs"][0]["replacement_product_id"] == replacement["id"]


def test_zero_view_rotation_never_duplicates_an_existing_quantity_zero_item(client) -> None:
    old_product = create_ready_product(client, "Old Zero View Lock", "rotation-old-lock")
    existing_zero = create_ready_product(client, "Existing Quantity Zero Connector", "rotation-existing-zero")
    clean_replacement = create_ready_product(client, "Clean Replacement Connector", "rotation-clean")
    for product in (existing_zero, clean_replacement):
        client.post(
            f"/products/{product['id']}/supplier",
            json={
                "supplier": "home_depot",
                "source_url": f"https://www.homedepot.com/p/{product['id']}",
                "last_price": 10.0,
                "last_shipping": 0.0,
                "in_stock": True,
            },
        ).raise_for_status()
        client.post(f"/products/{product['id']}/draft-price", json={"mode": "competitor"}).raise_for_status()
    client.post(
        f"/products/{old_product['id']}/mark-listed",
        json={"listing_id": "890000000011", "account_id": "a.m.anim-59", "status": "active"},
    ).raise_for_status()
    client.post(
        f"/products/{existing_zero['id']}/mark-listed",
        json={"listing_id": "890000000012", "account_id": "a.m.anim-59", "status": "active"},
    ).raise_for_status()
    client.post(
        "/ebay/sync-runs/listing-report",
        json={
            "account_key": "a.m.anim-59",
            "source": "rotation_test",
            "tombstone_missing": False,
            "rows": [
                {"listing_id": "890000000011", "sku": old_product["sku"], "quantity": "1", "status": "Active", "views": "0", "started_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()},
                {"listing_id": "890000000012", "sku": existing_zero["sku"], "quantity": "0", "status": "Active", "views": "0"},
            ],
        },
    ).raise_for_status()
    client.patch(
        "/settings/pricing",
        json={"auto_delist_zero_view_enabled": True, "auto_delist_zero_view_days": 29},
    ).raise_for_status()

    payload = client.post(
        "/listing-rotations/auto-queue?ebay_account_key=a.m.anim-59&limit=1"
    ).json()
    assert payload["queued"] == 1
    assert payload["pairs"][0]["replacement_product_id"] == clean_replacement["id"]


def test_queued_listing_is_blocked_if_supplier_becomes_unavailable(client) -> None:
    product = create_ready_product(client, "Availability Changed After Queue")
    job = client.post(
        "/listing-jobs",
        json={
            "product_ids": [product["id"]],
            "ebay_account_key": "a.m.anim-59",
            "action": "publish",
            "scheduled_for": "2099-08-02T19:00:00Z",
            "listing_schedule_at": "2099-08-02T19:00:00Z",
        },
    ).json()[0]
    client.patch(
        f"/products/{product['id']}/capture",
        json={"source_price": 12.0, "source_in_stock": False},
    ).raise_for_status()

    started = client.post(f"/listing-jobs/{job['id']}/run").json()["job"]

    assert started["status"] == "needs_review"
    assert "delivery is unavailable" in started["message"]


def test_listing_expansion_is_off_by_default(client) -> None:
    create_ready_product(client, "Expansion Off By Default", "expansion-off")
    queued = client.post("/listing-expansion/auto-queue?ebay_account_key=a.m.anim-59&limit=5")
    assert queued.status_code == 200
    payload = queued.json()
    assert payload == {"cap": 0, "active_count": 0, "headroom": 0, "eligible": 0, "queued": 0, "product_ids": []}


def test_listing_expansion_fills_headroom_with_the_most_profitable_candidate_first(client) -> None:
    # Cheaper source cost against a higher competitor price means a bigger margin;
    # low_profit uses the same known-good defaults as every other fixture in this file.
    high_profit = create_ready_product(
        client, "Expansion High Profit Widget", "expansion-high", source_price=5.0, competitor_price=40.0
    )
    low_profit = create_ready_product(client, "Expansion Low Profit Widget", "expansion-low")
    for product in (high_profit, low_profit):
        client.post(f"/products/{product['id']}/draft-price", json={"mode": "competitor"}).raise_for_status()
        package = client.get(f"/products/{product['id']}/ebay-package").json()
        assert package["meets_minimum_profit"] is True, package

    client.patch(
        "/settings/pricing",
        json={"active_listing_target_enabled": True, "active_listing_cap": 1},
    ).raise_for_status()

    queued = client.post("/listing-expansion/auto-queue?ebay_account_key=a.m.anim-59&limit=5")
    assert queued.status_code == 200
    payload = queued.json()
    assert payload["cap"] == 1
    assert payload["active_count"] == 0
    assert payload["headroom"] == 1
    assert payload["eligible"] == 2
    assert payload["queued"] == 1
    assert payload["product_ids"] == [high_profit["id"]]

    jobs = client.get("/listing-jobs").json()
    queued_product_ids = {job["product_id"] for job in jobs if job["action"] == "publish"}
    assert high_profit["id"] in queued_product_ids
    assert low_profit["id"] not in queued_product_ids


def test_listing_expansion_respects_existing_active_listings_against_the_cap(client) -> None:
    already_listed = create_ready_product(client, "Expansion Already Listed", "expansion-listed")
    client.post(
        f"/products/{already_listed['id']}/mark-listed",
        json={"listing_id": "890000000201", "account_id": "a.m.anim-59", "status": "active"},
    ).raise_for_status()
    client.post(
        "/ebay/sync-runs/listing-report",
        json={
            "account_key": "a.m.anim-59",
            "source": "expansion_test",
            "tombstone_missing": False,
            "rows": [{
                "listing_id": "890000000201",
                "sku": already_listed["sku"],
                "quantity": "1",
                "status": "Active",
                "views": "0",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }],
        },
    ).raise_for_status()

    candidate = create_ready_product(client, "Expansion New Candidate", "expansion-candidate")
    client.post(f"/products/{candidate['id']}/draft-price", json={"mode": "competitor"}).raise_for_status()

    client.patch(
        "/settings/pricing",
        json={"active_listing_target_enabled": True, "active_listing_cap": 1},
    ).raise_for_status()

    queued = client.post("/listing-expansion/auto-queue?ebay_account_key=a.m.anim-59&limit=5")
    payload = queued.json()
    assert payload["active_count"] == 1
    assert payload["headroom"] == 0
    assert payload["queued"] == 0


def test_listing_expansion_does_not_count_quantity_zero_listings_against_the_cap(client) -> None:
    # A listing correctly marked out of stock (quantity 0) keeps eBay status
    # "active" until tombstoned/restocked, but it isn't sellable -- it must not
    # occupy a cap slot that a real, in-stock listing could otherwise fill.
    out_of_stock = create_ready_product(client, "Expansion Out Of Stock", "expansion-oos")
    client.post(
        f"/products/{out_of_stock['id']}/mark-listed",
        json={"listing_id": "890000000301", "account_id": "a.m.anim-59", "status": "active"},
    ).raise_for_status()
    client.post(
        "/ebay/sync-runs/listing-report",
        json={
            "account_key": "a.m.anim-59",
            "source": "expansion_test",
            "tombstone_missing": False,
            "rows": [{
                "listing_id": "890000000301",
                "sku": out_of_stock["sku"],
                "quantity": "0",
                "status": "Active",
                "views": "0",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }],
        },
    ).raise_for_status()
    zeroed = next(item for item in client.get("/ebay/listings").json() if item["listing_id"] == "890000000301")
    assert zeroed["status"] == "active"
    assert zeroed["quantity"] == 0

    candidate = create_ready_product(client, "Expansion Fills Zeroed Slot", "expansion-fills-zeroed")
    client.post(f"/products/{candidate['id']}/draft-price", json={"mode": "competitor"}).raise_for_status()

    client.patch(
        "/settings/pricing",
        json={"active_listing_target_enabled": True, "active_listing_cap": 1},
    ).raise_for_status()

    queued = client.post("/listing-expansion/auto-queue?ebay_account_key=a.m.anim-59&limit=5")
    payload = queued.json()
    assert payload["active_count"] == 0
    assert payload["headroom"] == 1
    assert payload["queued"] == 1
    assert payload["product_ids"] == [candidate["id"]]

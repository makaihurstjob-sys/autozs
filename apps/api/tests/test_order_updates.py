def test_order_update_drafts_follow_fulfillment_lifecycle(client) -> None:
    order = client.post("/orders/sync-sandbox").json()

    first_run = client.post("/automation/order-update-drafts").json()

    assert first_run["drafted"] == 1
    assert first_run["updates"][0]["event"] == "order_received"
    assert first_run["updates"][0]["status"] == "draft"
    assert order["ebay_order_id"] in first_run["updates"][0]["subject"]

    duplicate = client.post(f"/orders/{order['id']}/customer-updates").json()
    assert duplicate["drafted"] == 0

    task_id = order["fulfillment_tasks"][0]["id"]
    client.patch(f"/fulfillment-tasks/{task_id}", json={"status": "in_progress", "note": "Ordering from supplier"})
    progress = client.post("/automation/order-update-drafts").json()

    assert progress["drafted"] == 1
    assert progress["updates"][0]["event"] == "fulfillment_started"
    assert "processing" in progress["updates"][0]["body"].lower()

    sent = client.patch(f"/customer-updates/{progress['updates'][0]['id']}", json={"status": "sent"}).json()
    assert sent["status"] == "sent"
    assert sent["sent_at"]

    drafts = client.get("/customer-updates?status=draft").json()
    assert {update["event"] for update in drafts} == {"order_received"}


def test_blocked_order_update_mentions_exception_reason(client) -> None:
    order = client.post("/orders/sync-sandbox").json()
    task_id = order["fulfillment_tasks"][0]["id"]
    client.patch(
        f"/fulfillment-tasks/{task_id}",
        json={"status": "blocked", "exception_reason": "supplier is out of stock"},
    )

    run = client.post("/automation/order-update-drafts").json()

    assert run["drafted"] == 1
    assert run["updates"][0]["event"] == "fulfillment_blocked"
    assert "supplier is out of stock" in run["updates"][0]["body"]

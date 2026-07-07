def test_push_config_disabled_without_vapid_keys(client):
    config = client.get("/push/config").json()

    assert config["enabled"] is False
    assert "reason" in config


def test_push_subscription_can_be_registered_and_updated(client):
    payload = {
        "endpoint": "https://push.example/sub/1",
        "keys": {"p256dh": "abc", "auth": "def"},
        "label": "iPhone",
        "user_agent": "Mobile Safari",
        "dashboard_url": "https://desktop/mobile.html",
    }

    created = client.post("/push/subscriptions", json=payload)
    assert created.status_code == 200

    updated = client.post("/push/subscriptions", json={**payload, "label": "iPhone Updated"})
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]

    subscriptions = client.get("/push/subscriptions").json()
    assert len(subscriptions) == 1
    assert subscriptions[0]["label"] == "iPhone Updated"


def test_push_subscription_requires_endpoint_and_keys(client):
    response = client.post("/push/subscriptions", json={"endpoint": "x", "keys": {}})

    assert response.status_code == 400


def test_push_dispatch_is_safe_without_vapid_keys(client):
    result = client.post("/push/dispatch-alerts").json()
    test = client.post("/push/test", json={"title": "Test", "body": "Body"}).json()

    assert result["sent"] == 0
    assert "message" in result
    assert test["sent"] == 0

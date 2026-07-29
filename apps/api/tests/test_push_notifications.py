from datetime import datetime

from cryptography.hazmat.primitives import serialization
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.domain import ListingJob, Order, OrderItem, Product, PushSubscription
from app.services import push_notifications
from app.services.push_notifications import _load_or_create_vapid_private_key, _weekly_summary_due


def test_push_config_disabled_without_vapid_keys(client):
    config = client.get("/push/config").json()

    assert config["enabled"] is False
    assert "reason" in config


def test_generated_vapid_private_key_is_persisted_and_reused(tmp_path):
    key_path = tmp_path / "autozs-vapid-private.pem"

    first = _load_or_create_vapid_private_key(key_path)
    second = _load_or_create_vapid_private_key(key_path)

    assert key_path.exists()
    assert first.private_numbers() == second.private_numbers()
    assert isinstance(
        serialization.load_pem_private_key(key_path.read_bytes(), password=None),
        type(first),
    )


def test_push_subscription_can_be_registered_and_updated(client):
    payload = {
        "endpoint": "https://push.example/sub/1",
        "keys": {"p256dh": "abc", "auth": "def"},
        "label": "iPhone",
        "user_agent": "Mobile Safari",
        "dashboard_url": "https://desktop/mobile.html",
        "vapid_public_key": "public-key-1",
        "preferences": {"listing_completed": True, "delivery_mode": "grouped"},
    }

    created = client.post("/push/subscriptions", json=payload)
    assert created.status_code == 200

    updated = client.post("/push/subscriptions", json={**payload, "label": "iPhone Updated"})
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]

    subscriptions = client.get("/push/subscriptions").json()
    assert len(subscriptions) == 1
    assert subscriptions[0]["label"] == "iPhone Updated"
    assert subscriptions[0]["vapid_public_key"] == "public-key-1"
    assert subscriptions[0]["preferences"]["listing_completed"] is True
    assert subscriptions[0]["preferences"]["delivery_mode"] == "grouped"

    patched = client.patch(
        f"/push/subscriptions/{created.json()['id']}",
        json={
            "preferences": {"listing_queued": False},
            "timezone": "America/New_York",
            "weekly_summary_day": 5,
            "weekly_summary_time": "17:30",
            "weekly_summary_enabled": False,
        },
    )
    assert patched.status_code == 200
    assert patched.json()["preferences"]["listing_queued"] is False
    assert patched.json()["preferences"]["listing_completed"] is True
    assert patched.json()["weekly_summary_time"] == "17:30"
    assert patched.json()["weekly_summary_enabled"] is False


def test_push_subscription_requires_endpoint_and_keys(client):
    response = client.post("/push/subscriptions", json={"endpoint": "x", "keys": {}})

    assert response.status_code == 400


def test_push_dispatch_is_safe_without_vapid_keys(client):
    result = client.post("/push/dispatch-alerts").json()
    test = client.post("/push/test", json={"title": "Test", "body": "Body"}).json()

    assert result["sent"] == 0
    assert "message" in result
    assert test["sent"] == 0


def test_push_test_can_target_one_phone(client, monkeypatch):
    monkeypatch.setattr(push_notifications, "get_push_config", lambda: {"enabled": True, "reason": "", "public_key": "key"})
    delivered = []
    monkeypatch.setattr(push_notifications, "_send_payload", lambda subscription, payload: delivered.append(subscription.endpoint))
    first = client.post("/push/subscriptions", json={
        "endpoint": "https://push.example/sub/first",
        "keys": {"p256dh": "abc", "auth": "def"},
        "vapid_public_key": "key",
    }).json()
    client.post("/push/subscriptions", json={
        "endpoint": "https://push.example/sub/second",
        "keys": {"p256dh": "ghi", "auth": "jkl"},
        "vapid_public_key": "key",
    })

    result = client.post("/push/test", json={
        "title": "Targeted",
        "body": "Only one phone",
        "subscription_id": first["id"],
    }).json()

    assert result["attempted"] == 1
    assert result["sent"] == 1
    assert delivered == ["https://push.example/sub/first"]


def test_weekly_summary_runs_once_after_local_saturday_time():
    subscription = PushSubscription(
        endpoint="https://push.example/sub/weekly",
        p256dh="abc",
        auth="def",
        timezone="America/New_York",
        weekly_summary_day=5,
        weekly_summary_time="18:00",
        weekly_summary_enabled=True,
    )
    saturday_after = datetime(2026, 7, 18, 22, 5)

    assert _weekly_summary_due(subscription, saturday_after) is True

    subscription.last_weekly_summary_at = datetime(2026, 7, 18, 22, 1)
    assert _weekly_summary_due(subscription, saturday_after) is False


def test_job_notifications_only_send_after_a_new_transition(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(push_notifications, "get_push_config", lambda: {"enabled": True, "reason": "", "public_key": "key"})
    delivered = []
    monkeypatch.setattr(push_notifications, "_send_payload", lambda subscription, payload: delivered.append(payload["title"]))

    with Session(engine) as db:
        product = Product(sku="PUSH-1", title="Push Test Product")
        db.add(product)
        db.flush()
        job = ListingJob(product_id=product.id, status="queued")
        db.add(job)
        db.commit()
        push_notifications.upsert_push_subscription(
            db,
            endpoint="https://push.example/sub/job",
            p256dh="abc",
            auth="def",
            vapid_public_key="key",
        )

        initial = push_notifications.dispatch_job_transition_notifications(db)
        assert initial["sent"] == 0

        job.status = "running"
        db.commit()
        changed = push_notifications.dispatch_job_transition_notifications(db)
        duplicate = push_notifications.dispatch_job_transition_notifications(db)

    assert changed["sent"] == 1
    assert duplicate["sent"] == 0
    assert delivered == ["Listing running"]


def test_new_real_order_sends_one_hype_notification(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(push_notifications, "get_push_config", lambda: {"enabled": True, "reason": "", "public_key": "key"})
    delivered = []
    monkeypatch.setattr(push_notifications, "_send_payload", lambda subscription, payload: delivered.append(payload))

    with Session(engine) as db:
        push_notifications.upsert_push_subscription(
            db,
            endpoint="https://push.example/sub/sale",
            p256dh="abc",
            auth="def",
            vapid_public_key="key",
        )
        order = Order(
            ebay_order_id="12-34567-89012",
            account_id="main-store",
            status="imported",
            total=20.96,
        )
        db.add(order)
        db.flush()
        db.add(OrderItem(
            order_id=order.id,
            title="First Real Sale Product",
            quantity=1,
            sale_price=19.53,
        ))
        db.commit()
        order_id = order.id

        first = push_notifications.dispatch_order_sale_notifications(db)
        duplicate = push_notifications.dispatch_order_sale_notifications(db)

    assert first["sent"] == 1
    assert duplicate["sent"] == 0
    assert delivered == [{
        "title": "💸💸 Sold Listing!!! 💸💸",
        "body": "You sold First Real Sale Product for $19.53! Open AutoZS to fulfill it.",
        "tag": f"autozs-order-sold-{order_id}",
        "url": "/mobile.html",
    }]


def test_existing_orders_are_seeded_for_a_new_phone(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(push_notifications, "get_push_config", lambda: {"enabled": True, "reason": "", "public_key": "key"})
    delivered = []
    monkeypatch.setattr(push_notifications, "_send_payload", lambda subscription, payload: delivered.append(payload))

    with Session(engine) as db:
        db.add(Order(
            ebay_order_id="12-34567-89013",
            account_id="main-store",
            status="imported",
            total=11.53,
        ))
        db.commit()
        push_notifications.upsert_push_subscription(
            db,
            endpoint="https://push.example/sub/new-phone",
            p256dh="abc",
            auth="def",
            vapid_public_key="key",
        )

        result = push_notifications.dispatch_order_sale_notifications(db)

    assert result["sent"] == 0
    assert delivered == []


def test_sale_notification_dev_test_uses_latest_real_order(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(push_notifications, "get_push_config", lambda: {"enabled": True, "reason": "", "public_key": "key"})
    delivered = []
    monkeypatch.setattr(push_notifications, "_send_payload", lambda subscription, payload: delivered.append(payload))

    with Session(engine) as db:
        subscription = push_notifications.upsert_push_subscription(
            db,
            endpoint="https://push.example/sub/dev-sale",
            p256dh="abc",
            auth="def",
            vapid_public_key="key",
        )
        order = Order(
            ebay_order_id="12-34567-89014",
            account_id="main-store",
            status="imported",
            total=6.02,
        )
        db.add(order)
        db.flush()
        db.add(OrderItem(
            order_id=order.id,
            title="Instagram Story Sale",
            quantity=1,
            sale_price=5.53,
        ))
        db.commit()

        result = push_notifications.send_latest_order_sale_test(
            db,
            subscription_id=subscription.id,
        )

    assert result["sent"] == 1
    assert delivered[0]["title"] == "💸💸 Sold Listing!!! 💸💸"
    assert delivered[0]["body"] == "You sold Instagram Story Sale for $5.53! Open AutoZS to fulfill it."

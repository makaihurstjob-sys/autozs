from datetime import datetime, timedelta

from app.services.workers import computed_worker_status


def test_current_worker_endpoint_creates_heartbeat(client) -> None:
    worker = client.get("/workers/current").json()

    assert worker["worker_id"] == "local-worker"
    assert worker["role"] == "operations"
    assert worker["status"] == "online"
    assert worker["database_url"]
    assert worker["last_seen_at"]


def test_worker_heartbeat_updates_same_worker(client) -> None:
    first = client.post("/workers/heartbeat").json()
    second = client.post("/workers/heartbeat").json()
    workers = client.get("/workers").json()

    assert second["id"] == first["id"]
    assert len([worker for worker in workers if worker["worker_id"] == "local-worker"]) == 1
    assert second["status"] == "online"


def test_worker_status_ages_from_online_to_stale_to_offline() -> None:
    now = datetime(2026, 7, 1, 12, 0, 0)

    assert computed_worker_status(now - timedelta(seconds=90), now=now) == "online"
    assert computed_worker_status(now - timedelta(minutes=5), now=now) == "stale"
    assert computed_worker_status(now - timedelta(minutes=12), now=now) == "offline"
    assert computed_worker_status(None, now=now) == "offline"


def test_startup_heartbeat_does_not_break_in_memory_db(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

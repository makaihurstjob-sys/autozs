from datetime import datetime, timedelta
import platform as platform_module

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.domain import WorkerNode, WorkerStatus


ONLINE_AFTER = timedelta(minutes=2)
OFFLINE_AFTER = timedelta(minutes=10)


def current_worker_payload(api_url: str = "", message: str | None = None) -> dict[str, str | None]:
    settings = get_settings()
    return {
        "worker_id": settings.autozs_worker_id or "local-worker",
        "label": settings.autozs_worker_label or platform_module.node() or "Local Worker",
        "role": settings.autozs_worker_role or "operations",
        "platform": platform_module.platform(),
        "api_url": api_url,
        "database_url": settings.database_url,
        "chrome_executable_path": settings.autozs_chrome_executable_path,
        "chrome_profile_root": settings.autozs_chrome_profile_root,
        "ebay_profile_root": settings.autozs_ebay_profile_root,
        "home_depot_profile_root": settings.autozs_home_depot_profile_root,
        "message": message or "Heartbeat received.",
    }


def heartbeat_current_worker(db: Session, api_url: str = "", message: str | None = None) -> WorkerNode:
    return upsert_worker_heartbeat(db, current_worker_payload(api_url=api_url, message=message))


def upsert_worker_heartbeat(db: Session, values: dict[str, str | None]) -> WorkerNode:
    now = datetime.utcnow()
    worker_id = str(values.get("worker_id") or "local-worker")
    worker = db.scalar(select(WorkerNode).where(WorkerNode.worker_id == worker_id))
    if worker is None:
        worker = WorkerNode(worker_id=worker_id)
        db.add(worker)
    worker.label = str(values.get("label") or worker_id)
    worker.role = str(values.get("role") or "operations")
    worker.platform = str(values.get("platform") or "")
    worker.status = WorkerStatus.online.value
    worker.api_url = str(values.get("api_url") or "")
    worker.database_url = str(values.get("database_url") or "")
    worker.chrome_executable_path = str(values.get("chrome_executable_path") or "")
    worker.chrome_profile_root = str(values.get("chrome_profile_root") or "")
    worker.ebay_profile_root = str(values.get("ebay_profile_root") or "")
    worker.home_depot_profile_root = str(values.get("home_depot_profile_root") or "")
    worker.last_seen_at = now
    worker.last_checked_at = now
    worker.message = values.get("message") or "Heartbeat received."
    db.commit()
    db.refresh(worker)
    return worker


def list_workers(db: Session, now: datetime | None = None) -> list[dict[str, object]]:
    checked_at = now or datetime.utcnow()
    workers = db.scalars(select(WorkerNode).order_by(WorkerNode.last_seen_at.desc(), WorkerNode.worker_id)).all()
    return [serialize_worker(worker, now=checked_at) for worker in workers]


def read_current_worker(db: Session, now: datetime | None = None) -> dict[str, object]:
    payload = current_worker_payload()
    worker = db.scalar(select(WorkerNode).where(WorkerNode.worker_id == payload["worker_id"]))
    if worker is None:
        worker = heartbeat_current_worker(db, message="Registered current AutoZS worker.")
    return serialize_worker(worker, now=now or datetime.utcnow())


def serialize_worker(worker: WorkerNode, now: datetime | None = None) -> dict[str, object]:
    checked_at = now or datetime.utcnow()
    status = computed_worker_status(worker.last_seen_at, now=checked_at)
    worker.status = status
    worker.last_checked_at = checked_at
    return {
        "id": worker.id,
        "worker_id": worker.worker_id,
        "label": worker.label,
        "role": worker.role,
        "platform": worker.platform,
        "status": status,
        "api_url": worker.api_url,
        "database_url": worker.database_url,
        "chrome_executable_path": worker.chrome_executable_path,
        "chrome_profile_root": worker.chrome_profile_root,
        "ebay_profile_root": worker.ebay_profile_root,
        "home_depot_profile_root": worker.home_depot_profile_root,
        "last_seen_at": worker.last_seen_at,
        "last_checked_at": checked_at,
        "seconds_since_seen": seconds_since_seen(worker.last_seen_at, now=checked_at),
        "message": worker.message or "",
        "created_at": worker.created_at,
        "updated_at": worker.updated_at,
    }


def computed_worker_status(last_seen_at: datetime | None, now: datetime | None = None) -> str:
    if last_seen_at is None:
        return WorkerStatus.offline.value
    age = (now or datetime.utcnow()) - last_seen_at
    if age <= ONLINE_AFTER:
        return WorkerStatus.online.value
    if age <= OFFLINE_AFTER:
        return WorkerStatus.stale.value
    return WorkerStatus.offline.value


def seconds_since_seen(last_seen_at: datetime | None, now: datetime | None = None) -> int | None:
    if last_seen_at is None:
        return None
    return max(0, int(((now or datetime.utcnow()) - last_seen_at).total_seconds()))

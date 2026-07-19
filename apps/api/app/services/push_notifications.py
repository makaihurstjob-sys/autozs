from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, get_settings
from app.models.domain import (
    EbayListing,
    EbayListingViewSnapshot,
    EbayRevisionBatch,
    EbayRevisionJob,
    ListingJob,
    Order,
    OperationalAlert,
    OperationalAlertSeverity,
    OperationalAlertStatus,
    Product,
    PushDeliveryReceipt,
    PushSubscription,
    SourceRefreshJob,
)
from app.services.alerts import ACTIVE_STATUSES, refresh_operational_alerts

try:
    from pywebpush import WebPushException, webpush
except Exception:  # pragma: no cover - dependency may be absent in local dev
    WebPushException = Exception
    webpush = None


settings = get_settings()

DEFAULT_PUSH_PREFERENCES: dict[str, bool | str | int] = {
    "listing_queued": True,
    "listing_running": True,
    "listing_attention": True,
    "listing_completed": False,
    "source_queued": True,
    "source_running": True,
    "source_attention": True,
    "source_completed": False,
    "revision_queued": True,
    "revision_running": True,
    "revision_attention": True,
    "revision_completed": False,
    "worker_attention": True,
    "delivery_mode": "individual",
}
ATTENTION_STATUSES = {"failed", "needs_review", "paused"}
COMPLETED_STATUSES = {"completed", "saved_draft", "tombstoned", "cancelled"}


@lru_cache(maxsize=1)
def get_vapid_keys() -> tuple[str, str]:
    """Return the public key and private key/path used by Web Push."""
    if settings.autozs_push_vapid_public_key and settings.autozs_push_vapid_private_key:
        return settings.autozs_push_vapid_public_key, settings.autozs_push_vapid_private_key

    key_path = _vapid_key_path()
    if key_path is None:
        return "", ""
    private_key = _load_or_create_vapid_private_key(key_path)
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_key = base64.urlsafe_b64encode(public_bytes).decode("ascii").rstrip("=")
    return public_key, str(key_path)


def get_push_config() -> dict[str, Any]:
    if webpush is None:
        return {
            "enabled": False,
            "public_key": "",
            "subject": settings.autozs_push_vapid_subject,
            "reason": "pywebpush is not installed.",
        }
    try:
        public_key, private_key = get_vapid_keys()
    except Exception as exc:
        return {
            "enabled": False,
            "public_key": "",
            "subject": settings.autozs_push_vapid_subject,
            "reason": f"VAPID key setup failed: {exc}",
        }
    if not public_key or not private_key:
        return {
            "enabled": False,
            "public_key": "",
            "subject": settings.autozs_push_vapid_subject,
            "reason": "VAPID keys are not configured.",
        }
    return {
        "enabled": True,
        "public_key": public_key,
        "subject": settings.autozs_push_vapid_subject,
        "reason": "",
    }


def upsert_push_subscription(
    db: Session,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    label: str = "",
    user_agent: str = "",
    dashboard_url: str = "",
    vapid_public_key: str = "",
    preferences: dict[str, bool | str | int] | None = None,
) -> PushSubscription:
    now = datetime.utcnow()
    subscription = db.scalars(select(PushSubscription).where(PushSubscription.endpoint == endpoint)).first()
    registered_for_current_key = bool(subscription and vapid_public_key and subscription.vapid_public_key == vapid_public_key)
    if subscription is None:
        subscription = PushSubscription(endpoint=endpoint, p256dh=p256dh, auth=auth)
        db.add(subscription)
    subscription.p256dh = p256dh
    subscription.auth = auth
    subscription.label = label
    subscription.user_agent = user_agent
    subscription.dashboard_url = dashboard_url
    subscription.vapid_public_key = vapid_public_key
    subscription.preferences_json = json.dumps(normalize_push_preferences(preferences))
    subscription.timezone = str((preferences or {}).get("timezone") or subscription.timezone or "America/New_York")
    subscription.weekly_summary_day = int((preferences or {}).get("weekly_summary_day", subscription.weekly_summary_day if subscription.id else 5))
    subscription.weekly_summary_time = str((preferences or {}).get("weekly_summary_time") or subscription.weekly_summary_time or "18:00")
    subscription.weekly_summary_enabled = bool((preferences or {}).get("weekly_summary_enabled", subscription.weekly_summary_enabled if subscription.id else True))
    subscription.enabled = True
    subscription.last_seen_at = now
    subscription.last_error = None
    db.flush()
    if vapid_public_key and not registered_for_current_key:
        _seed_current_job_receipts(db, subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def list_push_subscriptions(db: Session) -> list[PushSubscription]:
    return list(
        db.scalars(
            select(PushSubscription).order_by(
                PushSubscription.enabled.desc(),
                PushSubscription.last_seen_at.desc(),
                PushSubscription.id.desc(),
            )
        ).all()
    )


def serialize_push_subscription(subscription: PushSubscription) -> dict[str, Any]:
    return {
        "id": subscription.id,
        "endpoint": subscription.endpoint,
        "label": subscription.label or "",
        "dashboard_url": subscription.dashboard_url or "",
        "vapid_public_key": subscription.vapid_public_key or "",
        "preferences": read_push_preferences(subscription),
        "timezone": subscription.timezone or "America/New_York",
        "weekly_summary_day": int(subscription.weekly_summary_day if subscription.weekly_summary_day is not None else 5),
        "weekly_summary_time": subscription.weekly_summary_time or "18:00",
        "weekly_summary_enabled": bool(subscription.weekly_summary_enabled),
        "enabled": bool(subscription.enabled),
        "last_seen_at": subscription.last_seen_at,
        "last_notified_at": subscription.last_notified_at,
        "last_weekly_summary_at": subscription.last_weekly_summary_at,
        "last_error": subscription.last_error,
        "created_at": subscription.created_at,
        "updated_at": subscription.updated_at,
    }


def update_push_subscription(
    db: Session,
    subscription: PushSubscription,
    *,
    enabled: bool | None = None,
    preferences: dict[str, bool | str | int] | None = None,
    timezone_name: str | None = None,
    weekly_summary_day: int | None = None,
    weekly_summary_time: str | None = None,
    weekly_summary_enabled: bool | None = None,
) -> PushSubscription:
    if enabled is not None:
        subscription.enabled = enabled
    if preferences is not None:
        subscription.preferences_json = json.dumps(normalize_push_preferences(preferences, current=read_push_preferences(subscription)))
    if timezone_name is not None:
        _timezone(timezone_name)
        subscription.timezone = timezone_name
    if weekly_summary_day is not None:
        subscription.weekly_summary_day = max(0, min(6, int(weekly_summary_day)))
    if weekly_summary_time is not None:
        subscription.weekly_summary_time = weekly_summary_time
    if weekly_summary_enabled is not None:
        subscription.weekly_summary_enabled = weekly_summary_enabled
    subscription.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(subscription)
    return subscription


def normalize_push_preferences(
    values: dict[str, bool | str | int] | None,
    *,
    current: dict[str, bool | str | int] | None = None,
) -> dict[str, bool | str | int]:
    normalized = dict(DEFAULT_PUSH_PREFERENCES)
    if current:
        normalized.update({key: value for key, value in current.items() if key in DEFAULT_PUSH_PREFERENCES})
    if values:
        normalized.update({key: value for key, value in values.items() if key in DEFAULT_PUSH_PREFERENCES})
    normalized["delivery_mode"] = "grouped" if normalized.get("delivery_mode") == "grouped" else "individual"
    for key, default in DEFAULT_PUSH_PREFERENCES.items():
        if isinstance(default, bool):
            normalized[key] = bool(normalized.get(key, default))
    return normalized


def read_push_preferences(subscription: PushSubscription) -> dict[str, bool | str | int]:
    try:
        saved = json.loads(subscription.preferences_json or "{}")
    except (TypeError, ValueError):
        saved = {}
    return normalize_push_preferences(saved if isinstance(saved, dict) else {})


def send_test_push(
    db: Session,
    *,
    title: str,
    body: str,
    subscription_id: int | None = None,
) -> dict[str, Any]:
    config = get_push_config()
    subscriptions = _enabled_subscriptions(db)
    if subscription_id is not None:
        subscriptions = [subscription for subscription in subscriptions if subscription.id == subscription_id]
    if not config["enabled"]:
        return _result(attempted=len(subscriptions), message=str(config["reason"]))
    if not subscriptions:
        return _result(message="No matching enabled push subscription.")
    payload = {"title": title, "body": body, "tag": "autozs-test", "url": "/mobile.html"}
    return _send_to_subscriptions(db, subscriptions, payload, notified_alerts=0)


def dispatch_alert_notifications(db: Session, limit: int = 20) -> dict[str, Any]:
    refresh_operational_alerts(db)
    subscriptions = _enabled_subscriptions(db)
    config = get_push_config()
    if not config["enabled"]:
        return _result(attempted=len(subscriptions), message=str(config["reason"]))
    if not subscriptions:
        return _result(message="No enabled push subscriptions.")

    alerts = list(db.scalars(
        select(OperationalAlert)
        .where(
            OperationalAlert.status.in_(ACTIVE_STATUSES),
            OperationalAlert.severity.in_([OperationalAlertSeverity.critical.value, OperationalAlertSeverity.warning.value]),
        )
        .order_by(OperationalAlert.severity.desc(), OperationalAlert.last_seen_at.desc(), OperationalAlert.id.desc())
        .limit(limit)
    ).all())
    if not alerts:
        return _result(message="No new active alerts to notify.")

    attempted = sent = failed = notified_alerts = 0
    for alert in alerts:
        alert_sent = False
        for subscription in subscriptions:
            if not _alert_enabled_for_subscription(subscription, alert):
                continue
            event_key = f"subscription:{subscription.id}:alert:{alert.id}:{alert.status}"
            if _has_receipt(db, event_key):
                continue
            attempted += 1
            if _send_one(db, subscription, _payload_for_alert(alert)):
                _record_receipt(db, subscription, event_key, "alert", alert.job_type or alert.source, alert.job_id, alert.status)
                sent += 1
                alert_sent = True
            else:
                failed += 1
        if alert_sent:
            alert.last_notified_at = datetime.utcnow()
            notified_alerts += 1
    db.commit()
    return _result(
        attempted=attempted,
        sent=sent,
        failed=failed,
        notified_alerts=notified_alerts,
        message=f"Notified {notified_alerts} alert(s).",
    )


def dispatch_job_transition_notifications(db: Session, limit: int = 250) -> dict[str, Any]:
    config = get_push_config()
    subscriptions = [
        subscription for subscription in _enabled_subscriptions(db)
        if subscription.vapid_public_key and subscription.vapid_public_key == config.get("public_key")
    ]
    if not config["enabled"]:
        return _result(attempted=len(subscriptions), message=str(config["reason"]))
    if not subscriptions:
        return _result(message="No enabled push subscriptions.")

    candidates = _job_event_candidates(db, limit=limit)
    attempted = sent = failed = 0
    for subscription in subscriptions:
        preferences = read_push_preferences(subscription)
        pending = [event for event in candidates if preferences.get(event["preference"], False) and not _has_receipt(db, event["key"](subscription.id))]
        if preferences.get("delivery_mode") == "grouped":
            groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for event in pending:
                groups.setdefault((event["kind"], event["group"]), []).append(event)
            for (kind, group), events in groups.items():
                attempted += 1
                payload = _grouped_job_payload(kind, group, events)
                if _send_one(db, subscription, payload):
                    sent += 1
                    for event in events:
                        _record_job_event_receipt(db, subscription, event)
                else:
                    failed += 1
        else:
            for event in pending:
                attempted += 1
                if _send_one(db, subscription, event["payload"]):
                    sent += 1
                    _record_job_event_receipt(db, subscription, event)
                else:
                    failed += 1
    db.commit()
    return _result(attempted=attempted, sent=sent, failed=failed, message=f"Sent {sent} job update(s).")


def dispatch_weekly_summaries(db: Session, now: datetime | None = None) -> dict[str, Any]:
    config = get_push_config()
    subscriptions = [
        subscription for subscription in _enabled_subscriptions(db)
        if subscription.vapid_public_key and subscription.vapid_public_key == config.get("public_key")
    ]
    if not config["enabled"]:
        return _result(attempted=len(subscriptions), message=str(config["reason"]))
    checked_at = now or datetime.utcnow()
    attempted = sent = failed = 0
    for subscription in subscriptions:
        if not _weekly_summary_due(subscription, checked_at):
            continue
        attempted += 1
        if _send_one(db, subscription, _weekly_summary_payload(db, checked_at)):
            subscription.last_weekly_summary_at = checked_at
            sent += 1
        else:
            failed += 1
    db.commit()
    return _result(attempted=attempted, sent=sent, failed=failed, message=f"Sent {sent} weekly summary notification(s).")


def dispatch_push_cycle(db: Session) -> dict[str, Any]:
    alert_result = dispatch_alert_notifications(db)
    job_result = dispatch_job_transition_notifications(db)
    weekly_result = dispatch_weekly_summaries(db)
    return _result(
        attempted=int(alert_result["attempted"]) + int(job_result["attempted"]) + int(weekly_result["attempted"]),
        sent=int(alert_result["sent"]) + int(job_result["sent"]) + int(weekly_result["sent"]),
        failed=int(alert_result["failed"]) + int(job_result["failed"]) + int(weekly_result["failed"]),
        notified_alerts=int(alert_result["notified_alerts"]),
        message="Push cycle complete.",
    )


def _enabled_subscriptions(db: Session) -> list[PushSubscription]:
    return list(db.scalars(select(PushSubscription).where(PushSubscription.enabled.is_(True))).all())


def _alert_enabled_for_subscription(subscription: PushSubscription, alert: OperationalAlert) -> bool:
    preferences = read_push_preferences(subscription)
    if alert.source == "listing-job":
        return bool(preferences.get("listing_attention"))
    if alert.source in {"source-refresh", "supplier"}:
        return bool(preferences.get("source_attention"))
    if alert.source == "ebay-revision":
        return bool(preferences.get("revision_attention"))
    if alert.source == "worker":
        return bool(preferences.get("worker_attention"))
    return True


def _status_group(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized in {"queued", "prepared"}:
        return "queued"
    if normalized in {"running", "uploading", "waiting_results"}:
        return "running"
    if normalized in ATTENTION_STATUSES:
        return "attention"
    if normalized in COMPLETED_STATUSES:
        return "completed"
    return ""


def _job_event_candidates(db: Session, limit: int) -> list[dict[str, Any]]:
    rows: list[tuple[str, Any]] = []
    rows.extend(("listing", job) for job in db.scalars(select(ListingJob).order_by(ListingJob.updated_at.desc()).limit(limit)).all())
    rows.extend(("source", job) for job in db.scalars(select(SourceRefreshJob).order_by(SourceRefreshJob.updated_at.desc()).limit(limit)).all())
    rows.extend(("revision", job) for job in db.scalars(select(EbayRevisionJob).order_by(EbayRevisionJob.updated_at.desc()).limit(limit)).all())
    rows.extend(("revision_batch", job) for job in db.scalars(select(EbayRevisionBatch).order_by(EbayRevisionBatch.updated_at.desc()).limit(limit)).all())
    events: list[dict[str, Any]] = []
    for kind, job in rows:
        group = _status_group(job.status)
        if not group:
            continue
        product_id = getattr(job, "product_id", None)
        product = db.get(Product, product_id) if product_id is not None else None
        title = product.title if product is not None else (
            getattr(job, "filename", None) or getattr(job, "batch_key", None) or f"Revision batch {job.id}"
            if kind == "revision_batch" else f"Product {product_id}"
        )
        attempts = int(getattr(job, "attempts", 0) or 0)
        preference_kind = "revision" if kind == "revision_batch" else kind
        event = {
            "kind": kind,
            "group": group,
            "preference": f"{preference_kind}_{group}",
            "job_id": job.id,
            "status": job.status,
            "attempts": attempts,
            "title": title,
            "key": lambda subscription_id, kind=kind, job_id=job.id, group=group, attempts=attempts: (
                f"subscription:{subscription_id}:job:{kind}:{job_id}:{group}:{attempts}"
            ),
            "payload": _job_payload(kind, group, job, title),
        }
        events.append(event)
    return events


def _seed_current_job_receipts(db: Session, subscription: PushSubscription) -> None:
    """Start a newly registered phone at the current queue state without flooding it."""
    for event in _job_event_candidates(db, limit=500):
        _record_job_event_receipt(db, subscription, event)


def _job_payload(kind: str, group: str, job: Any, title: str) -> dict[str, Any]:
    kind_label = {"listing": "Listing", "source": "Source price", "revision": "eBay revision", "revision_batch": "eBay revision batch"}.get(kind, "Worker job")
    group_label = {"queued": "queued", "running": "running", "attention": "needs attention", "completed": "completed"}[group]
    body = f"{title} is {group_label}."
    if getattr(job, "message", None):
        body = f"{body} {job.message}"
    return {
        "title": f"{kind_label} {group_label}",
        "body": body[:240],
        "tag": f"autozs-{kind}-{job.id}-{group}-{int(getattr(job, 'attempts', 0) or 0)}",
        "url": "/mobile.html?view=queue",
    }


def _grouped_job_payload(kind: str, group: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    kind_label = {"listing": "listing", "source": "source-price", "revision": "eBay revision", "revision_batch": "eBay revision batch"}.get(kind, "worker")
    group_label = {"queued": "queued", "running": "running", "attention": "need attention", "completed": "completed"}[group]
    return {
        "title": f"AutoZS {kind_label} update",
        "body": f"{len(events)} {kind_label} job{'s' if len(events) != 1 else ''} {group_label}.",
        "tag": f"autozs-group-{kind}-{group}",
        "url": "/mobile.html?view=queue",
    }


def _record_job_event_receipt(db: Session, subscription: PushSubscription, event: dict[str, Any]) -> None:
    _record_receipt(
        db,
        subscription,
        event["key"](subscription.id),
        "job-transition",
        event["kind"],
        event["job_id"],
        event["status"],
    )


def _has_receipt(db: Session, event_key: str) -> bool:
    return db.scalar(select(PushDeliveryReceipt.id).where(PushDeliveryReceipt.event_key == event_key)) is not None


def _record_receipt(
    db: Session,
    subscription: PushSubscription,
    event_key: str,
    event_type: str,
    job_type: str,
    job_id: int | None,
    status: str,
) -> None:
    if _has_receipt(db, event_key):
        return
    db.add(PushDeliveryReceipt(
        subscription_id=subscription.id,
        event_key=event_key,
        event_type=event_type,
        job_type=job_type,
        job_id=job_id,
        status=status,
    ))


def _weekly_summary_due(subscription: PushSubscription, now: datetime) -> bool:
    if not subscription.weekly_summary_enabled:
        return False
    zone = _timezone(subscription.timezone or "America/New_York")
    aware_now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    local_now = aware_now.astimezone(zone)
    if local_now.weekday() != int(subscription.weekly_summary_day if subscription.weekly_summary_day is not None else 5):
        return False
    try:
        hour, minute = [int(part) for part in (subscription.weekly_summary_time or "18:00").split(":", 1)]
    except (TypeError, ValueError):
        hour, minute = 18, 0
    if (local_now.hour, local_now.minute) < (hour, minute):
        return False
    if subscription.last_weekly_summary_at is None:
        return True
    last = subscription.last_weekly_summary_at.replace(tzinfo=timezone.utc).astimezone(zone)
    return last.date() != local_now.date()


def _weekly_summary_payload(db: Session, now: datetime) -> dict[str, Any]:
    cutoff = now - timedelta(days=7)
    views = _views_gained_since(db, cutoff)
    listings = int(db.scalar(select(func.count(ListingJob.id)).where(ListingJob.status == "completed", ListingJob.completed_at >= cutoff)) or 0)
    scheduled = int(db.scalar(select(func.count(ListingJob.id)).where(ListingJob.listing_schedule_at >= now, ListingJob.status.in_(["queued", "running", "saved_draft", "completed"]))) or 0)
    orders = list(db.scalars(select(Order).where(Order.created_at >= cutoff, Order.status != "deleted")).all())
    attention = int(db.scalar(select(func.count(OperationalAlert.id)).where(OperationalAlert.status.in_(ACTIVE_STATUSES))) or 0)
    revenue = sum(float(order.total or 0) for order in orders)
    return {
        "title": "AutoZS weekly summary",
        "body": (
            f"{views} views gained · {listings} listings completed · {scheduled} scheduled · "
            f"{len(orders)} orders (${revenue:,.0f}) · {attention} need attention"
        ),
        "tag": "autozs-weekly-summary",
        "url": "/mobile.html",
    }


def _views_gained_since(db: Session, cutoff: datetime) -> int:
    listing_ids = list(db.scalars(select(EbayListing.id).where(EbayListing.status.in_(["active", "live", "listed", "scheduled"]))).all())
    if not listing_ids:
        return 0
    snapshots = list(db.scalars(
        select(EbayListingViewSnapshot)
        .where(EbayListingViewSnapshot.ebay_listing_id.in_(listing_ids), EbayListingViewSnapshot.captured_at >= cutoff)
        .order_by(EbayListingViewSnapshot.ebay_listing_id, EbayListingViewSnapshot.captured_at, EbayListingViewSnapshot.id)
    ).all())
    grouped: dict[int, list[EbayListingViewSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.ebay_listing_id, []).append(snapshot)
    return sum(
        sum(max(0, current.views - previous.views) for previous, current in zip(history, history[1:]))
        for history in grouped.values()
    )


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/New_York")


def _payload_for_alert(alert: OperationalAlert) -> dict[str, Any]:
    title = "AutoZS needs attention" if alert.severity == OperationalAlertSeverity.warning.value else "AutoZS critical alert"
    body = alert.title
    if alert.message:
        body = f"{alert.title}: {alert.message}"
    return {
        "title": title,
        "body": body[:240],
        "tag": f"autozs-alert-{alert.id}",
        "url": alert.action_url or "/mobile.html",
    }


def _send_to_subscriptions(
    db: Session,
    subscriptions: list[PushSubscription],
    payload: dict[str, Any],
    *,
    notified_alerts: int,
) -> dict[str, Any]:
    attempted = 0
    sent = 0
    failed = 0
    now = datetime.utcnow()
    for subscription in subscriptions:
        attempted += 1
        if _send_one(db, subscription, payload):
            sent += 1
            subscription.last_notified_at = now
        else:
            failed += 1
    db.commit()
    return _result(attempted=attempted, sent=sent, failed=failed, notified_alerts=notified_alerts)


def _send_one(db: Session, subscription: PushSubscription, payload: dict[str, Any]) -> bool:
    try:
        _send_payload(subscription, payload)
    except WebPushException as exc:
        subscription.last_error = str(exc)
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {404, 410}:
            subscription.enabled = False
        db.flush()
        return False
    except Exception as exc:  # pragma: no cover - depends on remote push service
        subscription.last_error = str(exc)
        db.flush()
        return False
    subscription.last_error = None
    subscription.last_notified_at = datetime.utcnow()
    db.flush()
    return True


def _send_payload(subscription: PushSubscription, payload: dict[str, Any]) -> None:
    if webpush is None:
        raise RuntimeError("pywebpush is not installed.")
    _, private_key = get_vapid_keys()
    if not private_key:
        raise RuntimeError("VAPID keys are not configured.")
    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
        data=json.dumps(payload),
        vapid_private_key=private_key,
        vapid_claims={"sub": settings.autozs_push_vapid_subject},
    )


def _vapid_key_path() -> Path | None:
    if settings.autozs_push_vapid_key_file:
        return Path(settings.autozs_push_vapid_key_file).expanduser()

    url = make_url(settings.database_url)
    if url.drivername.startswith("sqlite"):
        database = url.database or ""
        if database == ":memory:":
            return None
        database_path = Path(database).expanduser()
        if not database_path.is_absolute():
            database_path = PROJECT_ROOT / database_path
        return database_path.parent / "autozs-vapid-private.pem"
    return PROJECT_ROOT / "data" / "autozs-vapid-private.pem"


def _load_or_create_vapid_private_key(key_path: Path) -> ec.EllipticCurvePrivateKey:
    if key_path.exists():
        loaded = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if not isinstance(loaded, ec.EllipticCurvePrivateKey) or not isinstance(loaded.curve, ec.SECP256R1):
            raise ValueError("stored VAPID key is not a P-256 private key")
        return loaded

    key_path.parent.mkdir(parents=True, exist_ok=True)
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    try:
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _load_or_create_vapid_private_key(key_path)
    with os.fdopen(descriptor, "wb") as key_file:
        key_file.write(pem)
    return private_key


def _result(
    *,
    attempted: int = 0,
    sent: int = 0,
    failed: int = 0,
    notified_alerts: int = 0,
    message: str = "",
) -> dict[str, Any]:
    return {
        "attempted": attempted,
        "sent": sent,
        "failed": failed,
        "notified_alerts": notified_alerts,
        "message": message,
    }

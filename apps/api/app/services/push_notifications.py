from __future__ import annotations

import base64
from datetime import datetime
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, get_settings
from app.models.domain import (
    OperationalAlert,
    OperationalAlertSeverity,
    OperationalAlertStatus,
    PushSubscription,
)
from app.services.alerts import ACTIVE_STATUSES, refresh_operational_alerts

try:
    from pywebpush import WebPushException, webpush
except Exception:  # pragma: no cover - dependency may be absent in local dev
    WebPushException = Exception
    webpush = None


settings = get_settings()


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
) -> PushSubscription:
    now = datetime.utcnow()
    subscription = db.scalars(select(PushSubscription).where(PushSubscription.endpoint == endpoint)).first()
    if subscription is None:
        subscription = PushSubscription(endpoint=endpoint, p256dh=p256dh, auth=auth)
        db.add(subscription)
    subscription.p256dh = p256dh
    subscription.auth = auth
    subscription.label = label
    subscription.user_agent = user_agent
    subscription.dashboard_url = dashboard_url
    subscription.enabled = True
    subscription.last_seen_at = now
    subscription.last_error = None
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


def send_test_push(db: Session, *, title: str, body: str) -> dict[str, Any]:
    config = get_push_config()
    subscriptions = _enabled_subscriptions(db)
    if not config["enabled"]:
        return _result(attempted=len(subscriptions), message=str(config["reason"]))
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

    alerts = list(
        db.scalars(
            select(OperationalAlert)
            .where(
                OperationalAlert.status.in_(ACTIVE_STATUSES),
                OperationalAlert.severity.in_(
                    [OperationalAlertSeverity.critical.value, OperationalAlertSeverity.warning.value]
                ),
                or_(
                    OperationalAlert.last_notified_at.is_(None),
                    OperationalAlert.last_seen_at > OperationalAlert.last_notified_at,
                ),
            )
            .order_by(
                OperationalAlert.severity.desc(),
                OperationalAlert.last_seen_at.desc(),
                OperationalAlert.id.desc(),
            )
            .limit(limit)
        ).all()
    )
    if not alerts:
        return _result(message="No new active alerts to notify.")

    sent = 0
    failed = 0
    notified_alerts = 0
    now = datetime.utcnow()
    for alert in alerts:
        alert_result = _send_to_subscriptions(db, subscriptions, _payload_for_alert(alert), notified_alerts=0)
        sent += int(alert_result["sent"])
        failed += int(alert_result["failed"])
        if int(alert_result["sent"]) > 0:
            alert.last_notified_at = now
            notified_alerts += 1
    db.commit()
    return _result(
        attempted=len(alerts) * len(subscriptions),
        sent=sent,
        failed=failed,
        notified_alerts=notified_alerts,
        message=f"Notified {notified_alerts} alert(s).",
    )


def _enabled_subscriptions(db: Session) -> list[PushSubscription]:
    return list(db.scalars(select(PushSubscription).where(PushSubscription.enabled.is_(True))).all())


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
        try:
            _send_payload(subscription, payload)
        except WebPushException as exc:
            failed += 1
            subscription.last_error = str(exc)
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {404, 410}:
                subscription.enabled = False
        except Exception as exc:  # pragma: no cover - depends on remote push service
            failed += 1
            subscription.last_error = str(exc)
        else:
            sent += 1
            subscription.last_error = None
            subscription.last_notified_at = now
    db.commit()
    return _result(attempted=attempted, sent=sent, failed=failed, notified_alerts=notified_alerts)


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

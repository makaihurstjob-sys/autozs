from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import asyncio
import contextlib
import multiprocessing
import sys
from pathlib import Path

# Windows' multiprocessing "spawn" start method re-launches a child interpreter
# for uvicorn's server process, and without this it resolves to whatever
# "python.exe" the base install registered system-wide -- not this venv's
# interpreter -- even though sys.executable here is correct. That child then
# starts a second, environment-less AutoZS instance racing for the same
# ports. Pinning the executable explicitly is the standard fix.
multiprocessing.set_executable(sys.executable)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api.routes import router
from app.core.config import PROJECT_ROOT, get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.store_keys import DEFAULT_EBAY_STORE_KEY, LEGACY_DEFAULT_EBAY_STORE_KEY
from app.services.ebay_report_files import watch_ebay_report_inbox
from app.services.ebay_traffic import sync_ebay_traffic
from app.services.ebay_accounts import list_ebay_accounts
from app.services.ebay_sync import queue_ebay_traffic_sync
from app.services.listing_jobs import flag_stale_listing_jobs
from app.services.orders import reconcile_sold_listing_replacements
from app.services.push_notifications import dispatch_push_cycle
from app.services.settings import read_pricing_settings
from app.services.source_refresh_jobs import create_automatic_source_refresh_batch
from app.services.workers import heartbeat_current_worker
from app import models  # noqa: F401


settings = get_settings()
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)


def _ensure_lightweight_columns() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    migrations = {
        "orders": {
            "account_id": "VARCHAR(128) DEFAULT 'sandbox' NOT NULL",
            "recipient_name": "VARCHAR(256) DEFAULT '' NOT NULL",
            "shipping_address_line1": "VARCHAR(256) DEFAULT '' NOT NULL",
            "shipping_address_line2": "VARCHAR(256) DEFAULT '' NOT NULL",
            "shipping_city": "VARCHAR(128) DEFAULT '' NOT NULL",
            "shipping_state": "VARCHAR(64) DEFAULT '' NOT NULL",
            "shipping_postal_code": "VARCHAR(32) DEFAULT '' NOT NULL",
            "shipping_country": "VARCHAR(64) DEFAULT 'United States' NOT NULL",
            "sales_record_number": "VARCHAR(64)",
            "ebay_fee_amount": "FLOAT",
            "ebay_fee_evidence_ref": "VARCHAR(256) DEFAULT '' NOT NULL",
            "ebay_fee_recorded_at": "DATETIME",
        },
        "ebay_listings": {
            "account_id": "VARCHAR(128) DEFAULT 'sandbox' NOT NULL",
            "started_at": "DATETIME",
            "first_listed_at": "DATETIME",
            "renews_at": "DATETIME",
            "views": "INTEGER DEFAULT 0 NOT NULL",
            "view_delta": "INTEGER",
            "views_measured_at": "DATETIME",
            "removal_reason": "VARCHAR(64)",
            "removal_detail": "TEXT",
            "removed_at": "DATETIME",
            "relist_blocked": "BOOLEAN DEFAULT 0 NOT NULL",
        },
        "listing_jobs": {"listing_schedule_at": "DATETIME"},
        "operational_alerts": {"last_notified_at": "DATETIME"},
        "push_subscriptions": {
            "vapid_public_key": "TEXT DEFAULT '' NOT NULL",
            "preferences_json": "TEXT DEFAULT '{}' NOT NULL",
            "timezone": "VARCHAR(64) DEFAULT 'America/New_York' NOT NULL",
            "weekly_summary_day": "INTEGER DEFAULT 5 NOT NULL",
            "weekly_summary_time": "VARCHAR(5) DEFAULT '18:00' NOT NULL",
            "weekly_summary_enabled": "BOOLEAN DEFAULT 1 NOT NULL",
            "last_weekly_summary_at": "DATETIME",
        },
        "ebay_revision_jobs": {
            "source_price": "FLOAT",
            "source_shipping": "FLOAT DEFAULT 0 NOT NULL",
            "projected_profit": "FLOAT",
            "minimum_profit": "FLOAT",
            "guard_passed": "BOOLEAN DEFAULT 0 NOT NULL",
            "guard_reason": "TEXT",
            "approval_required": "BOOLEAN DEFAULT 1 NOT NULL",
            "approved_at": "DATETIME",
            "lease_expires_at": "DATETIME",
        },
        "products": {
            "listing_schedule_at": "DATETIME",
            "ebay_item_specifics_json": "TEXT DEFAULT '{}' NOT NULL",
            "capture_lease_owner": "VARCHAR(256)",
            "capture_lease_expires_at": "DATETIME",
        },
        "supplier_products": {
            "subscription_discount_percent": "FLOAT",
            "minimum_order_quantity": "INTEGER DEFAULT 1 NOT NULL",
            "price_unavailable": "BOOLEAN DEFAULT 0 NOT NULL",
        },
        "supplier_orders": {
            "approved_total": "FLOAT DEFAULT 0 NOT NULL",
            "checkout_token": "VARCHAR(128) DEFAULT '' NOT NULL",
        },
        "ebay_sync_runs": {
            "report_type": "VARCHAR(64) DEFAULT 'active_listings' NOT NULL",
            "report_reference": "VARCHAR(128)",
            "report_filename": "TEXT",
            "attempts": "INTEGER DEFAULT 0 NOT NULL",
        },
        "workers": {
            "api_url": "TEXT DEFAULT '' NOT NULL",
            "database_url": "TEXT DEFAULT '' NOT NULL",
            "chrome_executable_path": "TEXT DEFAULT '' NOT NULL",
            "chrome_profile_root": "TEXT DEFAULT '' NOT NULL",
            "ebay_profile_root": "TEXT DEFAULT '' NOT NULL",
            "home_depot_profile_root": "TEXT DEFAULT '' NOT NULL",
            "last_checked_at": "DATETIME",
        },
    }
    with engine.begin() as connection:
        for table, columns in migrations.items():
            if table not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
        if "ebay_revision_jobs" in existing_tables:
            connection.execute(
                text(
                    "UPDATE ebay_revision_jobs "
                    "SET status = 'needs_review', lease_expires_at = NULL, "
                    "message = 'Safety review required after AutoZS upgrade.' "
                    "WHERE status IN ('queued', 'running', 'paused') AND approved_at IS NULL"
                )
            )
        if "ebay_listings" in existing_tables:
            # One-time backfill for rows that predate first_listed_at. created_at is the
            # oldest immutable timestamp we have on the row, so it's the best available
            # floor for "how long has this actually been listed" until relists stop
            # clobbering started_at going forward.
            connection.execute(
                text(
                    "UPDATE ebay_listings SET first_listed_at = COALESCE(started_at, created_at) "
                    "WHERE first_listed_at IS NULL"
                )
            )
        legacy_store_columns = {
            "orders": ("account_id",),
            "ebay_listings": ("account_id",),
            "ebay_accounts": ("key",),
            "listing_jobs": ("ebay_account_key",),
            "ebay_revision_jobs": ("ebay_account_key",),
            "ebay_sync_runs": ("account_key",),
            "ebay_revision_templates": ("account_key",),
            "ebay_revision_batches": ("account_key",),
            "ebay_traffic_records": ("account_key", "account_id"),
            "customer_conversations": ("account_id",),
        }
        for table, columns in legacy_store_columns.items():
            if table not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table)}
            for column in columns:
                if column in existing_columns:
                    connection.execute(
                        text(f"UPDATE {table} SET {column} = :canonical WHERE {column} = :legacy"),
                        {
                            "canonical": DEFAULT_EBAY_STORE_KEY,
                            "legacy": LEGACY_DEFAULT_EBAY_STORE_KEY,
                        },
                    )
        if "ebay_accounts" in existing_tables:
            connection.execute(
                text(
                    "UPDATE ebay_accounts SET label = :canonical "
                    "WHERE key = :canonical AND lower(label) = :legacy_label"
                ),
                {
                    "canonical": DEFAULT_EBAY_STORE_KEY,
                    "legacy_label": LEGACY_DEFAULT_EBAY_STORE_KEY.replace("-", " "),
                },
            )


def _write_worker_heartbeat(message: str = "AutoZS API heartbeat.") -> None:
    with SessionLocal() as db:
        flag_stale_listing_jobs(db)
        reconcile_sold_listing_replacements(db)
        heartbeat_current_worker(db, message=message)


def _run_source_refresh_auto_queue() -> tuple[float, str]:
    with SessionLocal() as db:
        pricing_settings = read_pricing_settings(db)
        poll_minutes = max(1.0, float(pricing_settings.get("source_refresh_auto_poll_minutes", 5) or 5))
        if not bool(pricing_settings.get("source_refresh_auto_enabled", True)):
            return poll_minutes, "Automatic source refresh is disabled."
        _batch_key, _due_available, jobs, message = create_automatic_source_refresh_batch(db)
        if jobs:
            heartbeat_current_worker(db, message=message)
        return poll_minutes, message


async def _worker_heartbeat_loop() -> None:
    while True:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(_write_worker_heartbeat)
        await asyncio.sleep(60)


async def _source_refresh_auto_queue_loop() -> None:
    await asyncio.sleep(20)
    while True:
        poll_minutes = 5.0
        with contextlib.suppress(Exception):
            poll_minutes, _message = await asyncio.to_thread(_run_source_refresh_auto_queue)
        await asyncio.sleep(max(60, int(poll_minutes * 60)))


def _sync_ebay_traffic() -> None:
    with SessionLocal() as db:
        try:
            sync_ebay_traffic(db, selected_range="30", account="all")
        except ValueError:
            for account in list_ebay_accounts(db):
                account_key = str(account.get("key") or account.get("account_id") or "").strip()
                if account_key:
                    queue_ebay_traffic_sync(db, account_key=account_key)


async def _ebay_traffic_sync_loop() -> None:
    await asyncio.sleep(60)
    while True:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(_sync_ebay_traffic)
        await asyncio.sleep(6 * 60 * 60)


def _dispatch_push_alerts() -> None:
    with SessionLocal() as db:
        dispatch_push_cycle(db)


async def _push_alert_loop() -> None:
    await asyncio.sleep(10)
    while True:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(_dispatch_push_alerts)
        await asyncio.sleep(max(30, int(settings.autozs_push_alert_loop_seconds or 60)))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    _ensure_lightweight_columns()
    watcher = None
    heartbeat = None
    push_alerts = None
    source_refresh_scheduler = None
    traffic_scheduler = None
    with contextlib.suppress(Exception):
        await asyncio.to_thread(_write_worker_heartbeat, "AutoZS API started.")
    heartbeat = asyncio.create_task(_worker_heartbeat_loop())
    if ":memory:" not in settings.database_url:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(_dispatch_push_alerts)
        push_alerts = asyncio.create_task(_push_alert_loop())
        source_refresh_scheduler = asyncio.create_task(_source_refresh_auto_queue_loop())
        traffic_scheduler = asyncio.create_task(_ebay_traffic_sync_loop())
    if settings.ebay_report_watch_enabled and ":memory:" not in settings.database_url:
        watcher = asyncio.create_task(watch_ebay_report_inbox())
    try:
        yield
    finally:
        if heartbeat is not None:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
        if watcher is not None:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
        if push_alerts is not None:
            push_alerts.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await push_alerts
        if source_refresh_scheduler is not None:
            source_refresh_scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await source_refresh_scheduler
        if traffic_scheduler is not None:
            traffic_scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await traffic_scheduler


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def private_network_capture_headers(request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response
app.include_router(router)
app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import asyncio
import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api.routes import router
from app.core.config import PROJECT_ROOT, get_settings
from app.core.database import Base, SessionLocal, engine
from app.services.ebay_report_files import watch_ebay_report_inbox
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
        "orders": {"account_id": "VARCHAR(128) DEFAULT 'sandbox' NOT NULL"},
        "ebay_listings": {
            "account_id": "VARCHAR(128) DEFAULT 'sandbox' NOT NULL",
            "started_at": "DATETIME",
            "renews_at": "DATETIME",
            "views": "INTEGER DEFAULT 0 NOT NULL",
        },
        "listing_jobs": {"listing_schedule_at": "DATETIME"},
        "products": {"listing_schedule_at": "DATETIME"},
        "supplier_products": {"subscription_discount_percent": "FLOAT"},
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


def _write_worker_heartbeat(message: str = "AutoZS API heartbeat.") -> None:
    with SessionLocal() as db:
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


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    _ensure_lightweight_columns()
    watcher = None
    heartbeat = None
    source_refresh_scheduler = None
    with contextlib.suppress(Exception):
        await asyncio.to_thread(_write_worker_heartbeat, "AutoZS API started.")
    heartbeat = asyncio.create_task(_worker_heartbeat_loop())
    if ":memory:" not in settings.database_url:
        source_refresh_scheduler = asyncio.create_task(_source_refresh_auto_queue_loop())
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
        if source_refresh_scheduler is not None:
            source_refresh_scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await source_refresh_scheduler


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

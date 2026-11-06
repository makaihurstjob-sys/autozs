import importlib.util
from pathlib import Path
import sqlite3

import pytest

spec = importlib.util.spec_from_file_location("operations_idle", Path(__file__).with_name("check-operations-idle.py"))
idle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(idle)


def make_db():
    db = sqlite3.connect(":memory:")
    for table in idle.JOB_TABLES:
        db.execute(f"CREATE TABLE {table} (status TEXT)")
    db.execute("CREATE TABLE products (capture_lease_expires_at TEXT)")
    return db


def test_queued_and_terminal_rows_do_not_prevent_idle_recovery():
    db = make_db()
    for table in idle.JOB_TABLES:
        db.executemany(f"INSERT INTO {table} VALUES (?)", [(s,) for s in ("queued", "completed", "needs_review", "cancelled")])
    assert idle.busy_jobs(db) == {}


@pytest.mark.parametrize("table,status", [
    ("source_refresh_jobs", "running"), ("listing_jobs", "ready_to_save"),
    ("supplier_orders", "placing"), ("ebay_revision_batches", "waiting_results"),
    ("depop_listing_jobs", "submitting"), ("delivery_check_jobs", "running"),
])
def test_all_active_rows_are_checked_even_behind_old_history(table, status):
    db = make_db()
    db.execute(f"INSERT INTO {table} VALUES (?)", (status,))
    db.executemany(f"INSERT INTO {table} VALUES ('completed')", [() for _ in range(600)])
    assert idle.busy_jobs(db) == {table: 1}


def test_active_capture_lease_blocks_and_missing_schema_fails_closed():
    db = make_db()
    db.execute("INSERT INTO products VALUES (datetime('now', '+5 minutes'))")
    assert idle.busy_jobs(db) == {"product_capture_leases": 1}
    db.execute("DROP TABLE supplier_orders")
    with pytest.raises(sqlite3.OperationalError):
        idle.busy_jobs(db)

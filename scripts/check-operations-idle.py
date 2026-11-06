"""Read-only, full-table idle check before repairing the operations extension."""
import json
import sqlite3
import sys

JOB_TABLES = (
    "listing_jobs", "source_refresh_jobs", "ebay_revision_jobs",
    "ebay_revision_batches", "depop_listing_jobs", "delivery_check_jobs",
    "research_jobs", "ebay_sync_runs", "supplier_orders", "automation_runs",
)
BUSY_STATUSES = (
    "running", "processing", "in_progress", "placing", "submitting",
    "uploading", "waiting_results", "ready_to_save",
)


def busy_jobs(db):
    placeholders = ",".join("?" for _ in BUSY_STATUSES)
    active = {}
    for table in JOB_TABLES:
        count = db.execute(
            f"SELECT count(*) FROM {table} WHERE status IN ({placeholders})",
            BUSY_STATUSES,
        ).fetchone()[0]
        if count:
            active[table] = count
    captures = db.execute(
        "SELECT count(*) FROM products WHERE capture_lease_expires_at > datetime('now')"
    ).fetchone()[0]
    if captures:
        active["product_capture_leases"] = captures
    return active


if __name__ == "__main__":
    # No app import or environment loading: missing schema/read failures abort.
    with sqlite3.connect("file:C:/AutoZS/data/autozs.db?mode=ro", uri=True, timeout=5) as db:
        active = busy_jobs(db)
    print(json.dumps({"idle": not active, "active": active}))
    sys.exit(1 if active else 0)

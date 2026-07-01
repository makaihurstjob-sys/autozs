from app.workers.celery_app import celery_app
from app.workers import tasks


def test_catalog_cycle_is_registered_for_beat() -> None:
    schedule = celery_app.conf.beat_schedule["catalog-automation-cycle"]

    assert schedule["task"] == "automation.catalog_cycle"
    assert schedule["schedule"] >= 300
    assert tasks.run_catalog_cycle.name == "automation.catalog_cycle"


def test_operational_automation_tasks_are_registered_for_beat() -> None:
    schedule = celery_app.conf.beat_schedule

    assert schedule["source-monitoring-cycle"]["task"] == "automation.source_monitoring"
    assert schedule["listing-job-poll"]["task"] == "listing_jobs.start_next"
    assert schedule["sandbox-order-sync"]["task"] == "orders.sync_sandbox"
    assert schedule["draft-customer-updates"]["task"] == "orders.draft_customer_updates"
    assert tasks.run_source_monitoring.name == "automation.source_monitoring"
    assert tasks.start_next_listing_job_task.name == "listing_jobs.start_next"
    assert tasks.draft_customer_updates.name == "orders.draft_customer_updates"

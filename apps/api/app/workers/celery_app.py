from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("ebay_automation", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    beat_schedule={
        "catalog-automation-cycle": {
            "task": "automation.catalog_cycle",
            "schedule": max(settings.catalog_automation_interval_minutes, 5) * 60,
        },
        "source-monitoring-cycle": {
            "task": "automation.source_monitoring",
            "schedule": max(settings.catalog_automation_interval_minutes // 2, 15) * 60,
        },
        "listing-job-poll": {
            "task": "listing_jobs.start_next",
            "schedule": 10 * 60,
        },
        "sandbox-order-sync": {
            "task": "orders.sync_sandbox",
            "schedule": 30 * 60,
        },
        "draft-customer-updates": {
            "task": "orders.draft_customer_updates",
            "schedule": 15 * 60,
        },
    },
)
celery_app.autodiscover_tasks(["app.workers"])

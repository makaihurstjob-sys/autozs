from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.domain import ResearchJob
from app.services.listing_jobs import start_next_listing_job
from app.services.monitoring import run_source_monitoring_cycle
from app.services.automation import run_catalog_automation_cycle
from app.services.orders import seed_mock_order
from app.services.order_updates import generate_order_update_drafts
from app.services.research import create_mock_candidates
from app.workers.celery_app import celery_app


@celery_app.task(name="research.run_job")
def run_research_job(job_id: int) -> dict[str, str | int]:
    with SessionLocal() as db:
        job = db.get(ResearchJob, job_id)
        if job is None:
            return {"status": "missing", "job_id": job_id}
        created = create_mock_candidates(db, job)
        return {"status": "completed", "job_id": job_id, "created": len(created)}


@celery_app.task(name="orders.sync_sandbox")
def sync_sandbox_orders() -> dict[str, str]:
    with SessionLocal() as db:
        order = seed_mock_order(db)
        return {"status": "completed", "order_id": order.ebay_order_id}


@celery_app.task(name="automation.catalog_cycle")
def run_catalog_cycle() -> dict[str, int | str]:
    with SessionLocal() as db:
        result = run_catalog_automation_cycle(db)
        return {
            "status": "completed",
            "draft_prices_updated": result.draft_prices_updated,
            "repricing_snapshots": result.repricing_snapshots,
            "image_products_checked": result.image_products_checked,
            "image_products_attempted": result.image_products_attempted,
            "image_download_attempted": result.image_download_attempted,
            "image_downloaded": result.image_downloaded,
        }


@celery_app.task(name="automation.source_monitoring")
def run_source_monitoring() -> dict[str, int | str]:
    with SessionLocal() as db:
        result = run_source_monitoring_cycle(db)
        return {
            "status": "completed",
            "total": result.total,
            "needs_refresh": result.needs_refresh,
            "high_priority": result.high_priority,
            "medium_priority": result.medium_priority,
            "extension_ready": result.extension_ready,
            "run_id": result.run_id,
        }


@celery_app.task(name="orders.draft_customer_updates")
def draft_customer_updates() -> dict[str, int | str]:
    with SessionLocal() as db:
        updates = generate_order_update_drafts(db)
        return {"status": "completed", "drafted": len(updates)}


@celery_app.task(name="listing_jobs.start_next")
def start_next_listing_job_task(ebay_account_key: str | None = None) -> dict[str, int | str | None]:
    with SessionLocal() as db:
        job = start_next_listing_job(db, ebay_account_key=ebay_account_key)
        if job is None:
            return {"status": "empty", "job_id": None}
        return {"status": job.status, "job_id": job.id, "product_id": job.product_id}


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"

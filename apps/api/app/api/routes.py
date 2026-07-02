from datetime import datetime, timedelta
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.domain import (
    AutomationRun,
    CandidateProduct,
    Competitor,
    CustomerUpdate,
    EbayAccount,
    EbayListing,
    EbayRevisionJob,
    EbaySyncRun,
    FulfillmentTask,
    Order,
    PriceSnapshot,
    Product,
    ProductStatus,
    ResearchJob,
    SupplierProduct,
)
from app.schemas.domain import (
    CatalogAutomationRunRead,
    CatalogSettingsUpdate,
    AutomationRunRead,
    CandidateRead,
    CompetitorRead,
    CompetitorUpsert,
    CapturedProductUpdate,
    BulkProductImageDownloadResult,
    CapturedProductImport,
    CustomerUpdateRead,
    CustomerUpdateStatusPatch,
    DraftRecalculationResult,
    DraftPriceUpdate,
    EbayAccountRead,
    EbayAccountUpsert,
    EbayBrowserAccountReport,
    EbayBrowserAccountStatus,
    EbayListingPackage,
    EbayListingMarkRequest,
    EbayListingRead,
    EbaySyncListingReportImport,
    EbaySyncRunCreate,
    EbaySyncRunProgress,
    EbaySyncRunRead,
    EbayRevisionEnqueueRequest,
    EbayRevisionEnqueueResult,
    EbayRevisionJobRead,
    EbayRevisionJobUpdate,
    EbayExportResult,
    EbayApiPayload,
    EbayConnectionStatus,
    EbayManualMacro,
    EbayOAuthCallbackRequest,
    EbayOAuthStartRead,
    EbayOAuthTokenRead,
    EbayPublishResult,
    FulfillmentTaskRead,
    FulfillmentTaskUpdate,
    ListingQueueItem,
    ListingJobCreate,
    ListingDraftVerification,
    ListingJobRead,
    ListingJobRunResult,
    ListingJobUpdate,
    ListingReadinessReport,
    OrderUpdateDraftRunRead,
    OrderRead,
    PriceSnapshotRead,
    PricingSettingsUpdate,
    ProductImageDownloadResult,
    ProductImagePrepResult,
    ProductImportRequest,
    ProductListingScheduleUpdate,
    ProductImportResult,
    ProductRead,
    RepricingRunRead,
    RepricingSelectionRequest,
    ResearchJobCreate,
    ResearchJobRead,
    SettingsRead,
    SourceCaptureQueueItem,
    SourceCaptureQueueRead,
    SourceRefreshQueueItem,
    SourceRefreshQueueRead,
    SourceMonitoringRunRead,
    SourceRefreshBatchCreate,
    SourceRefreshBatchRead,
    SourceRefreshJobFailure,
    SourceRefreshJobRead,
    StatsImportPoint,
    StatsMixItem,
    StatsOverviewRead,
    StatsSeriesPoint,
    StatsTopProduct,
    StatsTotals,
    SupplierAttach,
    UiThemeUpdate,
    WorkerRead,
)
from app.services.importer import (
    build_ebay_listing_package,
    build_ebay_api_payload,
    build_ebay_manual_macro,
    build_listing_readiness,
    choose_product_draft_price,
    effective_supplier_cost,
    import_captured_product,
    download_missing_product_images,
    download_product_images,
    export_ebay_listing_files,
    import_products,
    listing_item_specifics,
    recalculate_all_draft_prices,
    split_urls,
    update_product_from_capture,
)
from app.services.listing_jobs import (
    enqueue_listing_jobs,
    list_listing_jobs as list_listing_jobs_service,
    read_listing_job,
    serialize_listing_job,
    start_listing_job,
    start_next_listing_job,
    update_listing_job,
    verify_listing_job_draft,
)
from app.services.automation import create_repricing_snapshots, run_catalog_automation_cycle as run_catalog_cycle_service
from app.services.ebay import complete_ebay_oauth, ebay_connection_status, publish_ebay_sandbox_listing, refresh_ebay_access_token, start_ebay_oauth
from app.services.ebay_accounts import create_ebay_account, delete_ebay_account, list_ebay_accounts, update_ebay_account
from app.services.ebay_browser_account import read_ebay_browser_account_status, update_ebay_browser_account_status
from app.services.ebay_revisions import (
    approve_ebay_revision_job,
    enqueue_ebay_price_revisions,
    list_ebay_revision_jobs,
    serialize_ebay_revision_job,
    start_next_ebay_revision_job,
    update_ebay_revision_job,
)
from app.services.ebay_sync import (
    import_listing_report_rows,
    list_ebay_sync_runs,
    serialize_ebay_sync_run,
    start_ebay_sync_run,
    update_ebay_sync_run_progress,
)
from app.services.images import prepare_product_images_for_ebay
from app.services.monitoring import build_source_refresh_queue, run_source_monitoring_cycle
from app.services.orders import seed_mock_order
from app.services.order_updates import generate_order_update_drafts, list_customer_updates, update_customer_update_status
from app.services.products import approve_candidate
from app.services.research import create_mock_candidates
from app.services.settings import read_pricing_settings, write_pricing_settings
from app.services.source_refresh_jobs import (
    claim_next_source_refresh_job_any_batch,
    claim_next_source_refresh_job,
    create_automatic_source_refresh_batch,
    complete_source_refresh_job,
    create_source_refresh_batch,
    fail_source_refresh_job,
    list_source_refresh_jobs,
    serialize_source_refresh_job,
    source_refresh_has_running_job,
)
from app.services.workers import heartbeat_current_worker, list_workers, read_current_worker

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/workers", response_model=list[WorkerRead])
def read_workers(db: Session = Depends(get_db)) -> list[WorkerRead]:
    return [WorkerRead(**worker) for worker in list_workers(db)]


@router.get("/workers/current", response_model=WorkerRead)
def read_current_worker_route(db: Session = Depends(get_db)) -> WorkerRead:
    return WorkerRead(**read_current_worker(db))


@router.post("/workers/heartbeat", response_model=WorkerRead)
def heartbeat_worker_route(db: Session = Depends(get_db)) -> WorkerRead:
    heartbeat_current_worker(db)
    return WorkerRead(**read_current_worker(db))


@router.get("/settings", response_model=SettingsRead)
def read_settings(db: Session = Depends(get_db)) -> SettingsRead:
    return SettingsRead(**read_pricing_settings(db))


@router.patch("/settings/pricing", response_model=SettingsRead)
def update_pricing_settings(payload: PricingSettingsUpdate, db: Session = Depends(get_db)) -> SettingsRead:
    values = write_pricing_settings(db, payload.model_dump())
    return SettingsRead(**values)


@router.patch("/settings/theme", response_model=SettingsRead)
def update_theme_settings(payload: UiThemeUpdate, db: Session = Depends(get_db)) -> SettingsRead:
    values = write_pricing_settings(db, payload.model_dump())
    return SettingsRead(**values)


@router.patch("/settings/catalog", response_model=SettingsRead)
def update_catalog_settings(payload: CatalogSettingsUpdate, db: Session = Depends(get_db)) -> SettingsRead:
    updates = payload.model_dump(exclude_none=True)
    for key in ("supplier_settings_json", "keyword_blacklist_json", "buyer_accounts_json", "marketing_settings_json"):
        if key not in updates:
            continue
        try:
            parsed = json.loads(updates[key])
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"{key} must contain valid JSON") from exc
        if key in {"supplier_settings_json", "marketing_settings_json"} and not isinstance(parsed, dict):
            raise HTTPException(status_code=422, detail=f"{key} must be an object")
        if key in {"keyword_blacklist_json", "buyer_accounts_json"} and not isinstance(parsed, list):
            raise HTTPException(status_code=422, detail=f"{key} must be a list")
        if key == "buyer_accounts_json":
            clean_accounts = []
            for account in parsed:
                if not isinstance(account, dict):
                    continue
                clean_accounts.append(
                    {
                        field: account.get(field, "")
                        for field in (
                            "id",
                            "label",
                            "supplier",
                            "region",
                            "username",
                            "billing_name",
                            "billing_zipcode",
                            "billing_phone",
                            "connection_mode",
                            "payment_method",
                            "max_pending_orders",
                            "daily_order_limit",
                            "auto_order",
                            "auto_tracking",
                            "order_scan",
                            "status",
                        )
                    }
                )
            updates[key] = json.dumps(clean_accounts, separators=(",", ":"))
        else:
            updates[key] = json.dumps(parsed, separators=(",", ":"))
    values = write_pricing_settings(db, updates)
    return SettingsRead(**values)


@router.get("/ebay/connection", response_model=EbayConnectionStatus)
def read_ebay_connection(db: Session = Depends(get_db)) -> EbayConnectionStatus:
    return EbayConnectionStatus(**ebay_connection_status(db))


@router.get("/ebay/accounts", response_model=list[EbayAccountRead])
def read_ebay_accounts(db: Session = Depends(get_db)) -> list[EbayAccountRead]:
    return [EbayAccountRead(**account) for account in list_ebay_accounts(db)]


@router.get("/ebay/browser-account", response_model=EbayBrowserAccountStatus)
def read_ebay_browser_account(account_key: str = "manual", db: Session = Depends(get_db)) -> EbayBrowserAccountStatus:
    return EbayBrowserAccountStatus(**read_ebay_browser_account_status(db, account_key=account_key))


@router.post("/ebay/browser-account", response_model=EbayBrowserAccountStatus)
def report_ebay_browser_account(payload: EbayBrowserAccountReport, db: Session = Depends(get_db)) -> EbayBrowserAccountStatus:
    return EbayBrowserAccountStatus(
        **update_ebay_browser_account_status(
            db,
            detected_username=payload.detected_username,
            url=payload.url,
            marketplace=payload.marketplace,
            source=payload.source,
            account_key=payload.account_key,
        )
    )


@router.post("/ebay/accounts", response_model=EbayAccountRead)
def create_ebay_account_route(payload: EbayAccountUpsert, db: Session = Depends(get_db)) -> EbayAccountRead:
    return EbayAccountRead(**create_ebay_account(db, payload.model_dump()))


@router.patch("/ebay/accounts/{account_key}", response_model=EbayAccountRead)
def update_ebay_account_route(account_key: str, payload: EbayAccountUpsert, db: Session = Depends(get_db)) -> EbayAccountRead:
    account = update_ebay_account(db, account_key, payload.model_dump())
    if account is None:
        raise HTTPException(status_code=404, detail="eBay account not found")
    return EbayAccountRead(**account)


@router.delete("/ebay/accounts/{account_key}")
def delete_ebay_account_route(account_key: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    if not delete_ebay_account(db, account_key):
        raise HTTPException(status_code=404, detail="eBay account not found")
    return {"deleted": True}


@router.post("/ebay/oauth/start", response_model=EbayOAuthStartRead)
def start_ebay_oauth_flow(db: Session = Depends(get_db)) -> EbayOAuthStartRead:
    result = start_ebay_oauth(db)
    if result.get("missing"):
        raise HTTPException(status_code=400, detail={"missing": result["missing"]})
    return EbayOAuthStartRead(**result)


@router.post("/ebay/oauth/callback", response_model=EbayOAuthTokenRead)
def complete_ebay_oauth_flow(payload: EbayOAuthCallbackRequest, db: Session = Depends(get_db)) -> EbayOAuthTokenRead:
    try:
        result = complete_ebay_oauth(db, payload.code, payload.state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EbayOAuthTokenRead(**result)


@router.get("/ebay/oauth/callback", response_model=EbayOAuthTokenRead)
def complete_ebay_oauth_redirect(code: str, state: str | None = None, db: Session = Depends(get_db)) -> EbayOAuthTokenRead:
    try:
        result = complete_ebay_oauth(db, code, state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EbayOAuthTokenRead(**result)


@router.post("/ebay/oauth/refresh", response_model=EbayOAuthTokenRead)
def refresh_ebay_oauth_token(db: Session = Depends(get_db)) -> EbayOAuthTokenRead:
    try:
        result = refresh_ebay_access_token(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EbayOAuthTokenRead(**result)


@router.post("/research/jobs", response_model=ResearchJobRead)
def create_research_job(payload: ResearchJobCreate, db: Session = Depends(get_db)) -> ResearchJob:
    job = ResearchJob(source=payload.source, query=payload.query, status="running")
    db.add(job)
    db.commit()
    db.refresh(job)
    create_mock_candidates(db, job)
    db.refresh(job)
    return job


@router.get("/research/jobs", response_model=list[ResearchJobRead])
def list_research_jobs(db: Session = Depends(get_db)) -> list[ResearchJob]:
    return list(db.scalars(select(ResearchJob).order_by(ResearchJob.created_at.desc())).all())


@router.get("/research/candidates", response_model=list[CandidateRead])
def list_candidates(status: str | None = None, db: Session = Depends(get_db)) -> list[CandidateProduct]:
    stmt = select(CandidateProduct).order_by(CandidateProduct.created_at.desc())
    if status:
        stmt = stmt.where(CandidateProduct.status == status)
    return list(db.scalars(stmt).all())


def _normalize_seller_username(username: str) -> str:
    cleaned = " ".join(str(username or "").strip().split())
    cleaned = cleaned.lstrip("@").strip()
    if "/" in cleaned:
        cleaned = cleaned.rstrip("/").split("/")[-1]
    if not cleaned:
        raise HTTPException(status_code=400, detail="Seller username is required")
    return cleaned[:128]


def _find_competitor(db: Session, username: str) -> Competitor | None:
    normalized = username.lower()
    competitors = db.scalars(select(Competitor)).all()
    return next((item for item in competitors if (item.username or "").lower() == normalized), None)


@router.get("/research/sellers", response_model=list[CompetitorRead])
def list_saved_sellers(db: Session = Depends(get_db)) -> list[Competitor]:
    return list(db.scalars(select(Competitor).order_by(Competitor.updated_at.desc(), Competitor.created_at.desc())).all())


@router.post("/research/sellers", response_model=CompetitorRead)
def save_research_seller(payload: CompetitorUpsert, db: Session = Depends(get_db)) -> Competitor:
    username = _normalize_seller_username(payload.username)
    competitor = _find_competitor(db, username)
    if competitor is None:
        competitor = Competitor(username=username)
        db.add(competitor)
    if payload.seed_listing_url:
        competitor.seed_listing_url = payload.seed_listing_url
    if payload.notes is not None:
        competitor.notes = payload.notes
    db.commit()
    db.refresh(competitor)
    return competitor


@router.delete("/research/sellers/{username}")
def delete_research_seller(username: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    competitor = _find_competitor(db, _normalize_seller_username(username))
    if competitor is None:
        raise HTTPException(status_code=404, detail="Seller not found")
    db.delete(competitor)
    db.commit()
    return {"deleted": True}


@router.post("/research/candidates/{candidate_id}/approve", response_model=ProductRead)
def approve_candidate_route(candidate_id: int, db: Session = Depends(get_db)) -> Product:
    candidate = db.get(CandidateProduct, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return approve_candidate(db, candidate)


@router.post("/research/candidates/{candidate_id}/reject", response_model=CandidateRead)
def reject_candidate_route(candidate_id: int, db: Session = Depends(get_db)) -> CandidateProduct:
    candidate = db.get(CandidateProduct, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate.status = "rejected"
    db.commit()
    db.refresh(candidate)
    return candidate


@router.get("/products", response_model=list[ProductRead])
def list_products(include_deleted: bool = Query(False), db: Session = Depends(get_db)) -> list[Product]:
    stmt = (
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .order_by(Product.created_at.desc())
    )
    if not include_deleted:
        stmt = stmt.where(Product.status != ProductStatus.deleted.value)
    return list(db.scalars(stmt).all())


@router.post("/products/import", response_model=ProductImportResult)
def import_source_products(payload: ProductImportRequest, db: Session = Depends(get_db)) -> ProductImportResult:
    urls = split_urls(payload.urls)
    if not urls:
        raise HTTPException(status_code=400, detail="Paste at least one source URL")
    products, warnings = import_products(
        db,
        urls,
        supplier_override=payload.supplier_override,
        source_price_override=payload.source_price_override,
        source_shipping_override=payload.source_shipping_override,
        competitor_price=payload.competitor_price,
    )
    return ProductImportResult(imported=len(products), products=[ProductRead.model_validate(product) for product in products], warnings=warnings)


@router.post("/products/import-captured", response_model=ProductRead)
def import_captured_source_product(payload: CapturedProductImport, db: Session = Depends(get_db)) -> Product:
    product = import_captured_product(
        db,
        source_url=payload.source_url,
        title=payload.title,
        source_price=payload.source_price,
        source_shipping=payload.source_shipping,
        competitor_price=payload.competitor_price,
        subscription_discount_percent=payload.subscription_discount_percent,
        description=payload.description,
        image_urls=payload.image_urls,
    )
    if payload.refresh_job_id:
        complete_source_refresh_job(db, payload.refresh_job_id, product.id)
    return product


@router.post("/source-refresh/batches", response_model=SourceRefreshBatchRead)
def create_refresh_batch(payload: SourceRefreshBatchCreate, db: Session = Depends(get_db)) -> SourceRefreshBatchRead:
    batch_key, due_available, jobs = create_source_refresh_batch(
        db,
        limit=payload.limit,
        interval_hours=payload.interval_hours,
        force=payload.force,
        product_ids=set(payload.product_ids) if payload.product_ids is not None else None,
    )
    first = claim_next_source_refresh_job(db, batch_key) if payload.auto_claim and jobs else None
    serialized = [SourceRefreshJobRead(**serialize_source_refresh_job(db, job)) for job in jobs]
    runner_url = serialize_source_refresh_job(db, first)["runner_url"] if first else None
    return SourceRefreshBatchRead(
        batch_key=batch_key,
        requested=payload.limit,
        queued=len(jobs),
        due_available=due_available,
        interval_hours=payload.interval_hours,
        runner_url=runner_url,
        jobs=serialized,
    )


@router.post("/source-refresh/batches/{batch_key}/next", response_model=SourceRefreshJobRead | None)
def claim_next_refresh_job(batch_key: str, db: Session = Depends(get_db)) -> SourceRefreshJobRead | None:
    job = claim_next_source_refresh_job(db, batch_key)
    return SourceRefreshJobRead(**serialize_source_refresh_job(db, job)) if job else None


@router.post("/source-refresh/jobs/next", response_model=SourceRefreshJobRead | None)
def claim_next_refresh_job_any_batch(db: Session = Depends(get_db)) -> SourceRefreshJobRead | None:
    job = claim_next_source_refresh_job_any_batch(db)
    return SourceRefreshJobRead(**serialize_source_refresh_job(db, job)) if job else None


@router.get("/source-refresh/jobs/running", response_model=dict[str, bool])
def read_source_refresh_running(db: Session = Depends(get_db)) -> dict[str, bool]:
    return {"running": source_refresh_has_running_job(db)}


@router.post("/source-refresh/auto-queue", response_model=SourceRefreshBatchRead)
def queue_automatic_source_refresh(db: Session = Depends(get_db)) -> SourceRefreshBatchRead:
    batch_key, due_available, jobs, _message = create_automatic_source_refresh_batch(db)
    serialized = [SourceRefreshJobRead(**serialize_source_refresh_job(db, job)) for job in jobs]
    return SourceRefreshBatchRead(
        batch_key=batch_key or "",
        requested=len(jobs),
        queued=len(jobs),
        due_available=due_available,
        interval_hours=float(read_pricing_settings(db).get("source_refresh_interval_hours", 6)),
        runner_url=None,
        jobs=serialized,
    )


@router.get("/source-refresh/jobs", response_model=list[SourceRefreshJobRead])
def read_source_refresh_jobs(
    batch_key: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[SourceRefreshJobRead]:
    return [
        SourceRefreshJobRead(**serialize_source_refresh_job(db, job))
        for job in list_source_refresh_jobs(db, batch_key=batch_key, limit=limit)
    ]


@router.post("/source-refresh/jobs/{job_id}/failed", response_model=SourceRefreshJobRead)
def mark_source_refresh_job_failed(
    job_id: int,
    payload: SourceRefreshJobFailure,
    db: Session = Depends(get_db),
) -> SourceRefreshJobRead:
    job = fail_source_refresh_job(db, job_id, payload.message)
    if job is None:
        raise HTTPException(status_code=404, detail="Source refresh job not found")
    return SourceRefreshJobRead(**serialize_source_refresh_job(db, job))


@router.get("/products/capture-queue", response_model=SourceCaptureQueueRead)
def source_capture_queue(db: Session = Depends(get_db)) -> SourceCaptureQueueRead:
    products = db.scalars(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.status != ProductStatus.deleted.value)
        .order_by(Product.updated_at.desc(), Product.created_at.desc())
    ).all()
    items: list[SourceCaptureQueueItem] = []
    for product in products:
        supplier = product.supplier_products[0] if product.supplier_products else None
        if supplier is None or not supplier.source_url:
            continue
        missing: list[str] = []
        if supplier.last_price is None:
            missing.append("source price")
        if supplier.last_shipping is None or supplier.last_shipping < 0:
            missing.append("source shipping")
        if not product.images:
            missing.append("images")
        elif any(image.local_path is None for image in product.images):
            missing.append("downloaded images")
        draft = product.listing_drafts[0] if product.listing_drafts else None
        if draft is None or not draft.description or "Review source details" in draft.description:
            missing.append("listing description")
        if not missing:
            continue
        items.append(
            SourceCaptureQueueItem(
                product_id=product.id,
                sku=product.sku,
                title=product.title,
                source_url=supplier.source_url,
                missing=missing,
                reason=f"Needs {', '.join(missing)}",
                source_price=supplier.last_price,
                source_shipping=supplier.last_shipping,
                image_count=len(product.images),
                local_image_count=sum(1 for image in product.images if image.local_path),
                item_specifics=listing_item_specifics(product, supplier),
                updated_at=supplier.updated_at,
            )
        )
    return SourceCaptureQueueRead(total=len(items), items=items)


@router.patch("/products/{product_id}/capture", response_model=ProductRead)
def update_product_capture(product_id: int, payload: CapturedProductUpdate, db: Session = Depends(get_db)) -> Product:
    product = update_product_from_capture(
        db,
        product_id=product_id,
        title=payload.title,
        source_price=payload.source_price,
        source_shipping=payload.source_shipping,
        competitor_price=payload.competitor_price,
        subscription_discount_percent=payload.subscription_discount_percent,
        description=payload.description,
        image_urls=payload.image_urls,
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/products/{product_id}/listing-schedule", response_model=ProductRead)
def update_product_listing_schedule(
    product_id: int, payload: ProductListingScheduleUpdate, db: Session = Depends(get_db)
) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product.listing_schedule_at = payload.listing_schedule_at
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/recalculate-drafts", response_model=DraftRecalculationResult)
def recalculate_drafts(db: Session = Depends(get_db)) -> DraftRecalculationResult:
    products = recalculate_all_draft_prices(db)
    updated = sum(1 for product in products if product.listing_drafts and product.listing_drafts[0].calculated_price is not None)
    queued, revision_updated = enqueue_ebay_price_revisions(db)
    return DraftRecalculationResult(
        updated=updated,
        products=[ProductRead.model_validate(product) for product in products],
        revision_jobs_queued=queued,
        revision_jobs_updated=revision_updated,
    )


@router.post("/products/{product_id}/draft-price", response_model=ProductRead)
def choose_draft_price(product_id: int, payload: DraftPriceUpdate, db: Session = Depends(get_db)) -> Product:
    product = choose_product_draft_price(db, product_id, payload.mode)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.delete("/products/{product_id}", response_model=ProductRead)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> Product:
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id == product_id)
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product.status = ProductStatus.deleted.value
    db.commit()
    db.refresh(product)
    return product


@router.get("/products/{product_id}/price-history", response_model=list[PriceSnapshotRead])
def read_product_price_history(product_id: int, db: Session = Depends(get_db)) -> list[PriceSnapshot]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return list(
        db.scalars(
            select(PriceSnapshot)
            .where(PriceSnapshot.product_id == product_id)
            .order_by(PriceSnapshot.created_at.desc(), PriceSnapshot.id.desc())
            .limit(200)
        ).all()
    )


@router.post("/products/{product_id}/download-images", response_model=ProductImageDownloadResult)
def download_images(product_id: int, db: Session = Depends(get_db)) -> ProductImageDownloadResult:
    result = download_product_images(db, product_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found")
    attempted, downloaded, images = result
    return ProductImageDownloadResult(product_id=product_id, attempted=attempted, downloaded=downloaded, images=images)


@router.post("/products/{product_id}/prepare-images", response_model=ProductImagePrepResult)
def prepare_images(product_id: int, size: int = Query(1000, ge=500, le=2000), db: Session = Depends(get_db)) -> ProductImagePrepResult:
    result = prepare_product_images_for_ebay(db, product_id, size=size)
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found")
    attempted, prepared, images = result
    return ProductImagePrepResult(product_id=product_id, attempted=attempted, prepared=prepared, size=size, images=images)


@router.post("/products/download-missing-images", response_model=BulkProductImageDownloadResult)
def download_missing_images(db: Session = Depends(get_db)) -> BulkProductImageDownloadResult:
    checked, attempted_products, attempted, downloaded, results = download_missing_product_images(db)
    return BulkProductImageDownloadResult(
        products_checked=checked,
        products_attempted=attempted_products,
        attempted=attempted,
        downloaded=downloaded,
        results=[
            ProductImageDownloadResult(product_id=product_id, attempted=product_attempted, downloaded=product_downloaded, images=images)
            for product_id, product_attempted, product_downloaded, images in results
        ],
    )


@router.post("/automation/catalog-cycle", response_model=CatalogAutomationRunRead)
def run_catalog_automation_cycle(db: Session = Depends(get_db)) -> CatalogAutomationRunRead:
    result = run_catalog_cycle_service(db)
    return CatalogAutomationRunRead(
        draft_prices_updated=result.draft_prices_updated,
        repricing_snapshots=result.repricing_snapshots,
        image_products_checked=result.image_products_checked,
        image_products_attempted=result.image_products_attempted,
        image_download_attempted=result.image_download_attempted,
        image_downloaded=result.image_downloaded,
    )


@router.post("/automation/source-monitoring-cycle", response_model=SourceMonitoringRunRead)
def run_source_monitoring(stale_after_days: int | None = Query(None, ge=1, le=90), db: Session = Depends(get_db)) -> SourceMonitoringRunRead:
    result = run_source_monitoring_cycle(db, stale_after_days=stale_after_days)
    return SourceMonitoringRunRead(
        stale_after_days=result.stale_after_days,
        stale_after_hours=result.stale_after_hours,
        total=result.total,
        needs_refresh=result.needs_refresh,
        high_priority=result.high_priority,
        medium_priority=result.medium_priority,
        extension_ready=result.extension_ready,
        run_id=result.run_id,
        message=result.message,
        items=[SourceRefreshQueueItem(**item.__dict__) for item in result.items],
    )


@router.post("/automation/order-update-drafts", response_model=OrderUpdateDraftRunRead)
def draft_order_customer_updates(db: Session = Depends(get_db)) -> OrderUpdateDraftRunRead:
    updates = generate_order_update_drafts(db)
    return OrderUpdateDraftRunRead(drafted=len(updates), updates=updates)


@router.get("/automation/runs", response_model=list[AutomationRunRead])
def list_automation_runs(limit: int = Query(25, ge=1, le=100), db: Session = Depends(get_db)) -> list[AutomationRun]:
    return list(
        db.scalars(
            select(AutomationRun)
            .order_by(AutomationRun.created_at.desc(), AutomationRun.id.desc())
            .limit(limit)
        ).all()
    )


@router.get("/products/{product_id}/ebay-package", response_model=EbayListingPackage)
def read_ebay_listing_package(product_id: int, db: Session = Depends(get_db)) -> EbayListingPackage:
    package = build_ebay_listing_package(db, product_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return EbayListingPackage(**package)


@router.get("/products/{product_id}/ebay-api-payload", response_model=EbayApiPayload)
def read_ebay_api_payload(product_id: int, db: Session = Depends(get_db)) -> EbayApiPayload:
    payload = build_ebay_api_payload(db, product_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return EbayApiPayload(**payload)


@router.get("/products/{product_id}/ebay-manual-macro", response_model=EbayManualMacro)
def read_ebay_manual_macro(product_id: int, db: Session = Depends(get_db)) -> EbayManualMacro:
    macro = build_ebay_manual_macro(db, product_id)
    if macro is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return EbayManualMacro(**macro)


@router.post("/products/{product_id}/publish-ebay-sandbox", response_model=EbayPublishResult)
def publish_product_to_ebay_sandbox(product_id: int, db: Session = Depends(get_db)) -> EbayPublishResult:
    try:
        result = publish_ebay_sandbox_listing(db, product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EbayPublishResult(**result)


@router.get("/ebay/listings", response_model=list[EbayListingRead])
def list_ebay_listings(db: Session = Depends(get_db)) -> list[EbayListingRead]:
    settings = read_pricing_settings(db)
    listings = db.scalars(select(EbayListing).order_by(EbayListing.created_at.desc(), EbayListing.id.desc())).all()
    return [EbayListingRead(**_serialize_ebay_listing(listing, settings)) for listing in listings]


@router.get("/ebay/sync-runs", response_model=list[EbaySyncRunRead])
def read_ebay_sync_runs(
    account_key: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[EbaySyncRunRead]:
    runs = list_ebay_sync_runs(db, account_key=account_key, limit=limit)
    return [EbaySyncRunRead(**serialize_ebay_sync_run(run)) for run in runs]


def _serialize_ebay_listing(listing: EbayListing, settings: dict) -> dict:
    return {
        "id": listing.id,
        "product_id": listing.product_id,
        "listing_id": listing.listing_id,
        "account_id": listing.account_id,
        "environment": listing.environment,
        "price": listing.price,
        "quantity": listing.quantity,
        "status": listing.status,
        "started_at": listing.started_at,
        "renews_at": listing.renews_at,
        "views": listing.views or 0,
        "days_until_relist": _days_until(listing.renews_at),
        "auto_delist_candidate": _auto_delist_candidate(listing, settings),
        "created_at": listing.created_at,
        "updated_at": listing.updated_at,
    }


def _serialize_listing_queue_renewal(listing: EbayListing, settings: dict) -> dict:
    return {
        "listing_started_at": listing.started_at,
        "listing_renews_at": listing.renews_at,
        "listing_views": listing.views or 0,
        "days_until_relist": _days_until(listing.renews_at),
        "auto_delist_candidate": _auto_delist_candidate(listing, settings),
    }


def _days_until(value: datetime | None) -> int | None:
    if value is None:
        return None
    delta = value - datetime.utcnow()
    return max(0, delta.days + (1 if delta.seconds or delta.microseconds else 0))


def _auto_delist_candidate(listing: EbayListing, settings: dict) -> bool:
    if not settings.get("auto_delist_zero_view_enabled"):
        return False
    if (listing.views or 0) > 0 or listing.status not in {"active", "live", "listed"}:
        return False
    started = listing.started_at or listing.created_at
    age_days = (datetime.utcnow() - started).total_seconds() / 86400
    return age_days >= float(settings.get("auto_delist_zero_view_days") or 25)


@router.post("/ebay/sync-runs", response_model=EbaySyncRunRead)
def create_ebay_sync_run(payload: EbaySyncRunCreate, db: Session = Depends(get_db)) -> EbaySyncRunRead:
    run = start_ebay_sync_run(db, account_key=payload.account_key, source=payload.source)
    return EbaySyncRunRead(**serialize_ebay_sync_run(run))


@router.post("/ebay/sync-runs/listing-report", response_model=EbaySyncRunRead)
def import_ebay_listing_report(payload: EbaySyncListingReportImport, db: Session = Depends(get_db)) -> EbaySyncRunRead:
    rows = [row.model_dump(exclude_none=True) for row in payload.rows]
    run = import_listing_report_rows(
        db,
        rows=rows,
        account_key=payload.account_key,
        run_id=payload.run_id,
        source=payload.source,
        tombstone_missing=payload.tombstone_missing,
    )
    return EbaySyncRunRead(**serialize_ebay_sync_run(run))


@router.get("/ebay/sync-runs/{run_id}", response_model=EbaySyncRunRead)
def read_ebay_sync_run(run_id: int, db: Session = Depends(get_db)) -> EbaySyncRunRead:
    run = db.get(EbaySyncRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="eBay sync run not found")
    return EbaySyncRunRead(**serialize_ebay_sync_run(run))


@router.patch("/ebay/sync-runs/{run_id}", response_model=EbaySyncRunRead)
def patch_ebay_sync_run(run_id: int, payload: EbaySyncRunProgress, db: Session = Depends(get_db)) -> EbaySyncRunRead:
    try:
        run = update_ebay_sync_run_progress(db, run_id, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="eBay sync run not found")
    return EbaySyncRunRead(**serialize_ebay_sync_run(run))


@router.post("/products/{product_id}/mark-listed", response_model=EbayListingRead)
def mark_product_listed(product_id: int, payload: EbayListingMarkRequest, db: Session = Depends(get_db)) -> EbayListing:
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.listing_drafts))
        .where(Product.id == product_id)
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    package = build_ebay_listing_package(db, product_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Product not found")
    listing_id = (payload.listing_id or f"MANUAL-{product.sku}")[:128]
    listing = db.scalar(
        select(EbayListing).where(
            EbayListing.product_id == product_id,
            EbayListing.listing_id == listing_id,
        )
    )
    if listing is None:
        listing = EbayListing(product_id=product_id, listing_id=listing_id)
        db.add(listing)
    listing.account_id = payload.account_id[:128]
    listing.environment = payload.environment[:32]
    listing.price = package["price"]
    listing.quantity = payload.quantity
    listing.status = payload.status[:32]
    if product.listing_drafts:
        product.listing_drafts[0].status = payload.status[:32]
    db.commit()
    db.refresh(listing)
    return listing


@router.get("/listings/queue", response_model=list[ListingQueueItem])
def list_listing_queue(db: Session = Depends(get_db)) -> list[ListingQueueItem]:
    settings = read_pricing_settings(db)
    product_ids = db.scalars(
        select(Product.id)
        .where(Product.status != ProductStatus.deleted.value)
        .order_by(Product.created_at.desc())
    ).all()
    items: list[ListingQueueItem] = []
    for product_id in product_ids:
        package = build_ebay_listing_package(db, product_id)
        readiness = build_listing_readiness(db, product_id) if package is not None else None
        if package is None or readiness is None:
            continue
        listing = db.scalar(
            select(EbayListing)
            .where(EbayListing.product_id == product_id)
            .order_by(EbayListing.created_at.desc(), EbayListing.id.desc())
        )
        listing_meta = _serialize_listing_queue_renewal(listing, settings) if listing else {}
        items.append(
            ListingQueueItem(
                product_id=product_id,
                sku=package["sku"],
                title=package["title"],
                price=package["price"],
                estimated_profit=package["estimated_profit"],
                meets_minimum_profit=package["meets_minimum_profit"],
                image_upload_status=package["image_upload_status"],
                image_count=len(package["image_urls"]),
                local_image_count=len(package["local_image_paths"]),
                manual_ready=readiness["manual_ready"],
                api_ready=readiness["api_ready"],
                missing_manual=readiness["missing_manual"],
                missing_api=readiness["missing_api"],
                warnings=readiness["warnings"],
                item_specifics=package["item_specifics"],
                source_url=package["source_url"],
                listing_id=listing.listing_id if listing else None,
                listing_status=listing.status if listing else None,
                listing_account_id=listing.account_id if listing else None,
                **listing_meta,
            )
        )
    return items


@router.get("/listing-jobs", response_model=list[ListingJobRead])
def list_listing_job_queue(
    status: str | None = None,
    limit: int = Query(100, ge=1, le=250),
    db: Session = Depends(get_db),
) -> list[ListingJobRead]:
    jobs = list_listing_jobs_service(db, status=status, limit=limit)
    return [ListingJobRead(**serialize_listing_job(db, job)) for job in jobs]


@router.post("/listing-jobs", response_model=list[ListingJobRead])
def create_listing_jobs(payload: ListingJobCreate, db: Session = Depends(get_db)) -> list[ListingJobRead]:
    jobs = enqueue_listing_jobs(
        db,
        product_ids=payload.product_ids,
        ebay_account_key=payload.ebay_account_key,
        action=payload.action,
        scheduled_for=payload.scheduled_for,
        listing_schedule_at=payload.listing_schedule_at,
    )
    if not jobs:
        raise HTTPException(status_code=404, detail="No matching products found")
    return [ListingJobRead(**serialize_listing_job(db, job)) for job in jobs]


@router.post("/listing-jobs/next", response_model=ListingJobRunResult)
def run_next_listing_job(
    ebay_account_key: str | None = None,
    db: Session = Depends(get_db),
) -> ListingJobRunResult:
    job = start_next_listing_job(db, ebay_account_key=ebay_account_key)
    if job is None:
        raise HTTPException(status_code=404, detail="No queued listing jobs are due")
    package = build_ebay_listing_package(
        db, job.product_id, job.listing_schedule_at.isoformat() if job.listing_schedule_at else None
    ) if job.status == "running" else None
    return ListingJobRunResult(job=ListingJobRead(**serialize_listing_job(db, job)), package=EbayListingPackage(**package) if package else None)


@router.post("/listing-jobs/{job_id}/run", response_model=ListingJobRunResult)
def run_listing_job(job_id: int, db: Session = Depends(get_db)) -> ListingJobRunResult:
    job = read_listing_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Listing job not found")
    job = start_listing_job(db, job)
    package = build_ebay_listing_package(
        db, job.product_id, job.listing_schedule_at.isoformat() if job.listing_schedule_at else None
    ) if job.status == "running" else None
    return ListingJobRunResult(job=ListingJobRead(**serialize_listing_job(db, job)), package=EbayListingPackage(**package) if package else None)


@router.patch("/listing-jobs/{job_id}", response_model=ListingJobRead)
def update_listing_job_route(job_id: int, payload: ListingJobUpdate, db: Session = Depends(get_db)) -> ListingJobRead:
    job = read_listing_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Listing job not found")
    updated = update_listing_job(
        db,
        job,
        status=payload.status,
        scheduled_for=payload.scheduled_for,
        listing_schedule_at=payload.listing_schedule_at,
        ebay_draft_id=payload.ebay_draft_id,
        listing_id=payload.listing_id,
        message=payload.message,
    )
    return ListingJobRead(**serialize_listing_job(db, updated))


@router.post("/listing-jobs/{job_id}/verify-draft", response_model=ListingJobRead)
def verify_listing_job_draft_route(job_id: int, payload: ListingDraftVerification, db: Session = Depends(get_db)) -> ListingJobRead:
    job = read_listing_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Listing job not found")
    updated = verify_listing_job_draft(
        db,
        job,
        exists=payload.exists,
        ebay_draft_id=payload.ebay_draft_id,
        url=payload.url,
        message=payload.message,
    )
    return ListingJobRead(**serialize_listing_job(db, updated))


@router.get("/products/{product_id}/listing-readiness", response_model=ListingReadinessReport)
def read_listing_readiness(product_id: int, db: Session = Depends(get_db)) -> ListingReadinessReport:
    report = build_listing_readiness(db, product_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return ListingReadinessReport(**report)


@router.post("/products/{product_id}/export-ebay", response_model=EbayExportResult)
def export_ebay_listing(product_id: int, db: Session = Depends(get_db)) -> EbayExportResult:
    result = export_ebay_listing_files(db, product_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return EbayExportResult(**result)


@router.get("/products/{product_id}/export-ebay.zip")
def download_ebay_export_zip(product_id: int, db: Session = Depends(get_db)) -> FileResponse:
    result = export_ebay_listing_files(db, product_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found")
    zip_path = Path(result["zip_path"])
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Export ZIP not found")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@router.post("/products/{product_id}/supplier", response_model=ProductRead)
def attach_supplier(product_id: int, payload: SupplierAttach, db: Session = Depends(get_db)) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    supplier = SupplierProduct(
        product_id=product.id,
        supplier=payload.supplier,
        source_url=payload.source_url,
        supplier_sku=payload.supplier_sku,
        last_price=payload.last_price,
        last_shipping=payload.last_shipping,
        subscription_discount_percent=payload.subscription_discount_percent,
        in_stock=payload.in_stock,
    )
    product.status = "monitoring"
    db.add(supplier)
    db.commit()
    stmt = (
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id == product.id)
    )
    return db.scalar(stmt)  # type: ignore[return-value]


@router.post("/repricing/run", response_model=RepricingRunRead)
def run_repricing(db: Session = Depends(get_db)) -> RepricingRunRead:
    snapshots = create_repricing_snapshots(db)
    return RepricingRunRead(updated=len(snapshots), snapshots=[PriceSnapshotRead.model_validate(s) for s in snapshots])


@router.post("/repricing/run-selected", response_model=RepricingRunRead)
def run_selected_repricing(payload: RepricingSelectionRequest, db: Session = Depends(get_db)) -> RepricingRunRead:
    recalculate_all_draft_prices(db, product_ids=payload.product_ids)
    snapshots = create_repricing_snapshots(db, product_ids=payload.product_ids)
    queued, revision_updated = enqueue_ebay_price_revisions(db, product_ids=payload.product_ids)
    return RepricingRunRead(
        updated=len(snapshots),
        snapshots=[PriceSnapshotRead.model_validate(s) for s in snapshots],
        revision_jobs_queued=queued,
        revision_jobs_updated=revision_updated,
    )


@router.get("/ebay/revision-jobs", response_model=list[EbayRevisionJobRead])
def read_ebay_revision_jobs(
    status: str | None = None,
    limit: int = Query(100, ge=1, le=250),
    db: Session = Depends(get_db),
) -> list[EbayRevisionJobRead]:
    jobs = list_ebay_revision_jobs(db, status=status, limit=limit)
    return [EbayRevisionJobRead(**serialize_ebay_revision_job(db, job)) for job in jobs]


@router.post("/ebay/revision-jobs/enqueue", response_model=EbayRevisionEnqueueResult)
def enqueue_ebay_revision_jobs(
    payload: EbayRevisionEnqueueRequest,
    db: Session = Depends(get_db),
) -> EbayRevisionEnqueueResult:
    queued, updated = enqueue_ebay_price_revisions(db, product_ids=payload.product_ids)
    return EbayRevisionEnqueueResult(queued=queued, updated=updated)


@router.post("/ebay/revision-jobs/next", response_model=EbayRevisionJobRead)
def run_next_ebay_revision_job(db: Session = Depends(get_db)) -> EbayRevisionJobRead:
    job = start_next_ebay_revision_job(db)
    if job is None:
        raise HTTPException(status_code=404, detail="No eBay price revisions are queued")
    return EbayRevisionJobRead(**serialize_ebay_revision_job(db, job))


@router.post("/ebay/revision-jobs/{job_id}/approve", response_model=EbayRevisionJobRead)
def approve_ebay_revision(job_id: int, db: Session = Depends(get_db)) -> EbayRevisionJobRead:
    job = db.get(EbayRevisionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="eBay revision job not found")
    try:
        approved = approve_ebay_revision_job(db, job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return EbayRevisionJobRead(**serialize_ebay_revision_job(db, approved))


@router.patch("/ebay/revision-jobs/{job_id}", response_model=EbayRevisionJobRead)
def patch_ebay_revision_job(
    job_id: int,
    payload: EbayRevisionJobUpdate,
    db: Session = Depends(get_db),
) -> EbayRevisionJobRead:
    job = db.get(EbayRevisionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="eBay revision job not found")
    try:
        updated = update_ebay_revision_job(db, job, status=payload.status, message=payload.message)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return EbayRevisionJobRead(**serialize_ebay_revision_job(db, updated))


@router.get("/repricing/source-refresh-queue", response_model=SourceRefreshQueueRead)
def source_refresh_queue(stale_after_days: int | None = Query(None, ge=1, le=90), db: Session = Depends(get_db)) -> SourceRefreshQueueRead:
    queue = build_source_refresh_queue(db, stale_after_days=stale_after_days)
    return SourceRefreshQueueRead(
        stale_after_days=queue.stale_after_days,
        stale_after_hours=queue.stale_after_hours,
        total=queue.total,
        needs_refresh=queue.needs_refresh,
        items=[SourceRefreshQueueItem(**item.__dict__) for item in queue.items],
    )


@router.get("/stats/overview", response_model=StatsOverviewRead)
def stats_overview(
    selected_range: str = Query("30", alias="range", pattern="^(7|30|90|all)$"),
    grain: str = Query("day", pattern="^(day|month)$"),
    account: str = Query("all", pattern="^[A-Za-z0-9_.:-]+$"),
    db: Session = Depends(get_db),
) -> StatsOverviewRead:
    settings = read_pricing_settings(db)
    products = db.scalars(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.status != ProductStatus.deleted.value)
    ).all()
    orders = db.scalars(select(Order).where(Order.status != "deleted")).all()
    listings = db.scalars(select(EbayListing).where(EbayListing.status.in_(("active", "listed", "live", "scheduled", "draft")))).all()
    snapshots = db.scalars(select(PriceSnapshot)).all()
    cutoff = _stats_cutoff(selected_range)

    products = [product for product in products if _in_stats_range(product.created_at, cutoff)]
    snapshots = [snapshot for snapshot in snapshots if _in_stats_range(snapshot.created_at, cutoff)]
    available_accounts = sorted(
        {
            *{order.account_id for order in orders if getattr(order, "account_id", None)},
            *{listing.account_id for listing in listings if getattr(listing, "account_id", None)},
            *{account.account_id for account in db.scalars(select(EbayAccount)).all() if getattr(account, "account_id", None)},
        }
    )
    if account != "all":
        account_orders = [order for order in orders if order.account_id == account and _in_stats_range(order.created_at, cutoff)]
        account_listings = [listing for listing in listings if listing.account_id == account and _in_stats_range(listing.created_at, cutoff)]
    else:
        account_orders = [order for order in orders if _in_stats_range(order.created_at, cutoff)]
        account_listings = [listing for listing in listings if _in_stats_range(listing.created_at, cutoff)]

    totals = {"catalog_revenue": 0.0, "catalog_cost": 0.0, "catalog_fees": 0.0, "expected_profit": 0.0}
    low_profit_products = 0
    series: dict[str, dict[str, float | str]] = {}
    import_series: dict[str, dict[str, int | str]] = {}
    shipping_mix = {"Free": 0, "Paid": 0, "Unknown": 0}
    pipeline_mix = {"Ready": 0, "Capture": 0, "Shipping": 0, "Images": 0, "No source": 0}
    listing_readiness_mix = {"Manual ready": 0, "API ready": 0, "Needs work": 0}
    top_products: list[StatsTopProduct] = []

    for product in products:
        supplier = product.supplier_products[0] if product.supplier_products else None
        draft = product.listing_drafts[0] if product.listing_drafts else None
        source_price = supplier.last_price if supplier else None
        source_shipping = supplier.last_shipping if supplier else -1.0
        draft_price = draft.calculated_price if draft else None
        cost = round(effective_supplier_cost(source_price, settings) + _shipping_cost(source_shipping), 2) if source_price is not None else 0.0
        fees = _stats_fees(product, draft_price)
        profit = _stats_profit(product, draft_price, source_price, source_shipping, settings)
        revenue = draft_price or 0.0
        totals["catalog_revenue"] += revenue
        totals["catalog_cost"] += cost
        totals["catalog_fees"] += fees or 0.0
        totals["expected_profit"] += profit or 0.0
        if profit is not None and profit < product.desired_profit:
            low_profit_products += 1

        label = _stats_period(product.created_at, grain)
        point = series.setdefault(label, {"label": label, "revenue": 0.0, "cost": 0.0, "fees": 0.0, "profit": 0.0})
        point["revenue"] = float(point["revenue"]) + revenue
        point["cost"] = float(point["cost"]) + cost
        point["fees"] = float(point["fees"]) + (fees or 0.0)
        point["profit"] = float(point["profit"]) + (profit or 0.0)
        import_point = import_series.setdefault(label, {"label": label, "count": 0})
        import_point["count"] = int(import_point["count"]) + 1

        if source_price is None:
            shipping_mix["Unknown"] += 1
        elif source_shipping < 0:
            shipping_mix["Unknown"] += 1
        elif source_shipping > 0:
            shipping_mix["Paid"] += 1
        else:
            shipping_mix["Free"] += 1

        stage = _stats_product_stage(product, supplier, draft)
        pipeline_mix[stage] += 1
        readiness = build_listing_readiness(db, product.id)
        if readiness and readiness["api_ready"]:
            listing_readiness_mix["API ready"] += 1
        elif readiness and readiness["manual_ready"]:
            listing_readiness_mix["Manual ready"] += 1
        else:
            listing_readiness_mix["Needs work"] += 1
        top_products.append(
            StatsTopProduct(
                product_id=product.id,
                sku=product.sku,
                title=product.title,
                source_price=source_price,
                source_shipping=source_shipping,
                draft_price=draft_price,
                expected_profit=profit,
                stage=stage,
            )
        )

    totals = {key: round(value, 2) for key, value in totals.items()}
    average_margin = (
        round((totals["expected_profit"] / totals["catalog_revenue"]) * 100, 1)
        if totals["catalog_revenue"]
        else None
    )
    return StatsOverviewRead(
        selected_range=selected_range,
        grain=grain,
        selected_account=account,
        available_accounts=["all", *available_accounts],
        account_note="Catalog projections are global; listing and synced order totals are filtered by eBay account.",
        totals=StatsTotals(
            catalog_revenue=totals["catalog_revenue"],
            catalog_cost=totals["catalog_cost"],
            catalog_fees=totals["catalog_fees"],
            expected_profit=totals["expected_profit"],
            imported_products=len(products),
            average_margin_percent=average_margin,
            low_profit_products=low_profit_products,
            source_snapshots=len(snapshots),
            order_revenue=round(sum(order.total for order in account_orders), 2),
            active_listings=len(account_listings),
            listed_value=round(sum(listing.price or 0.0 for listing in account_listings), 2),
        ),
        series=[
            StatsSeriesPoint(
                label=str(point["label"]),
                revenue=round(float(point["revenue"]), 2),
                cost=round(float(point["cost"]), 2),
                fees=round(float(point["fees"]), 2),
                profit=round(float(point["profit"]), 2),
            )
            for point in sorted(series.values(), key=lambda item: str(item["label"]))
        ],
        import_series=[
            StatsImportPoint(label=str(point["label"]), count=int(point["count"]))
            for point in sorted(import_series.values(), key=lambda item: str(item["label"]))
        ],
        shipping_mix=[StatsMixItem(label=label, value=value) for label, value in shipping_mix.items()],
        pipeline_mix=[StatsMixItem(label=label, value=value) for label, value in pipeline_mix.items()],
        listing_readiness_mix=[StatsMixItem(label=label, value=value) for label, value in listing_readiness_mix.items()],
        top_products=sorted(top_products, key=lambda product: product.expected_profit or 0.0, reverse=True)[:10],
    )


@router.get("/repricing/snapshots", response_model=list[PriceSnapshotRead])
def list_repricing_snapshots(db: Session = Depends(get_db)) -> list[PriceSnapshot]:
    return list(db.scalars(select(PriceSnapshot).order_by(PriceSnapshot.created_at.desc()).limit(100)).all())


@router.post("/orders/sync-sandbox", response_model=OrderRead)
def sync_sandbox_order(db: Session = Depends(get_db)) -> Order:
    return seed_mock_order(db)


@router.get("/orders", response_model=list[OrderRead])
def list_orders(include_sandbox: bool = False, db: Session = Depends(get_db)) -> list[Order]:
    stmt = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.fulfillment_tasks), selectinload(Order.customer_updates))
        .order_by(Order.created_at.desc())
    )
    if not include_sandbox:
        stmt = stmt.where(Order.ebay_order_id != "SANDBOX-ORDER-001")
    return list(db.scalars(stmt).all())


@router.post("/orders/{order_id}/customer-updates", response_model=OrderUpdateDraftRunRead)
def draft_order_customer_update(order_id: int, db: Session = Depends(get_db)) -> OrderUpdateDraftRunRead:
    if db.get(Order, order_id) is None:
        raise HTTPException(status_code=404, detail="Order not found")
    updates = generate_order_update_drafts(db, order_id=order_id)
    return OrderUpdateDraftRunRead(drafted=len(updates), updates=updates)


@router.get("/customer-updates", response_model=list[CustomerUpdateRead])
def read_customer_updates(status: str | None = Query(None, pattern="^(draft|sent|skipped)$"), db: Session = Depends(get_db)) -> list[CustomerUpdate]:
    return list_customer_updates(db, status=status)


@router.patch("/customer-updates/{update_id}", response_model=CustomerUpdateRead)
def update_customer_update(update_id: int, payload: CustomerUpdateStatusPatch, db: Session = Depends(get_db)) -> CustomerUpdate:
    update = update_customer_update_status(
        db,
        update_id,
        status=payload.status,
        subject=payload.subject,
        body=payload.body,
    )
    if update is None:
        raise HTTPException(status_code=404, detail="Customer update not found")
    return update


@router.patch("/fulfillment-tasks/{task_id}", response_model=FulfillmentTaskRead)
def update_fulfillment_task(
    task_id: int,
    payload: FulfillmentTaskUpdate,
    db: Session = Depends(get_db),
) -> FulfillmentTask:
    task = db.get(FulfillmentTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Fulfillment task not found")
    if payload.status is not None:
        task.status = payload.status
    if payload.note is not None:
        task.note = payload.note
    if payload.exception_reason is not None:
        task.exception_reason = payload.exception_reason
    db.commit()
    db.refresh(task)
    return task


def _stats_cutoff(selected_range: str) -> datetime | None:
    if selected_range == "all":
        return None
    return datetime.utcnow() - timedelta(days=int(selected_range))


def _in_stats_range(value: datetime | None, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    return bool(value and value >= cutoff)


def _stats_period(value: datetime | None, grain: str) -> str:
    if value is None:
        return "Unknown"
    if grain == "month":
        return value.strftime("%Y-%m")
    return value.strftime("%Y-%m-%d")


def _stats_profit(
    product: Product,
    draft_price: float | None,
    source_price: float | None,
    source_shipping: float,
    settings: dict[str, float | bool | str],
) -> float | None:
    if draft_price is None or source_price is None:
        return None
    fee_rate = product.ebay_fee_rate + product.promoted_rate + product.return_risk_rate
    return round(draft_price - effective_supplier_cost(source_price, settings) - _shipping_cost(source_shipping) - (draft_price * fee_rate), 2)


def _stats_fees(product: Product, draft_price: float | None) -> float | None:
    if draft_price is None:
        return None
    fee_rate = product.ebay_fee_rate + product.promoted_rate + product.return_risk_rate
    return round(draft_price * fee_rate, 2)


def _shipping_cost(value: float | None) -> float:
    if value is None or value < 0:
        return 0.0
    return float(value)


def _stats_product_stage(product: Product, supplier: SupplierProduct | None, draft) -> str:
    if supplier is None:
        return "No source"
    if supplier.last_price is None or draft is None or draft.calculated_price is None:
        return "Capture"
    if supplier.last_shipping is None or supplier.last_shipping < 0:
        return "Shipping"
    if not product.images or any(not image.local_path for image in product.images):
        return "Images"
    return "Ready"

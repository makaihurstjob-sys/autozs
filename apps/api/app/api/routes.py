from datetime import date, datetime, timedelta, timezone
import base64
import hmac
import json
from pathlib import Path
import re
import shutil
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.config import get_settings
from app.core.store_keys import DEFAULT_EBAY_STORE_KEY
from app.models.domain import (
    AutomationRun,
    CandidateProduct,
    Competitor,
    CustomerConversation,
    CustomerMessage,
    CustomerUpdate,
    EbayAccount,
    EbayListing,
    EbayListingViewSnapshot,
    EbayRevisionBatch,
    EbayRevisionJob,
    EbaySyncRun,
    FinancialAccount,
    FulfillmentTask,
    GiftCard,
    ListingDraft,
    Order,
    PriceSnapshot,
    Product,
    ProductImage,
    ProductStatus,
    PushSubscription,
    ResearchJob,
    SourceRefreshJob,
    SubscriptionExpense,
    SupplierOrder,
    SupplierProduct,
)
from app.models.depop import (
    DepopAccount,
    DepopListingJob,
    DepopListingVariant,
    DepopSourcePhoto,
)
from app.schemas.depop import (
    AmazonCaptureImport,
    DepopAccountRead,
    DepopAccountUpsert,
    DepopImportResult,
    DepopJobCreate,
    DepopJobRead,
    DepopJobUpdate,
    DepopPhotoDecision,
    DepopPhotoQueueItem,
    DepopPhotoReviewRead,
    DepopSourcePhotoRead,
    DepopVariantCreate,
    DepopVariantRead,
    DepopVariantUpdate,
)
from app.schemas.z_finance import ZFinanceSyncRequest
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
    CustomerConversationImport,
    CustomerConversationRead,
    CustomerMessageCreate,
    CustomerMessageRead,
    CustomerMessageUpdate,
    CustomerTemplateMessageCreate,
    CustomerTemplateRead,
    CustomerTemplateRenderRead,
    CustomerTemplateRenderRequest,
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
    EbayListingViewsCapture,
    EbayListingViewsCaptureResult,
    EbayListingViewsSummary,
    EbayListingViewSnapshotRead,
    EbayOrderReportImport,
    EbayOrderReportImportResult,
    EbayTrafficImportResult,
    EbayTrafficFileImport,
    EbayTrafficOverviewRead,
    EbayTrafficReportImport,
    EbayTrafficSyncResult,
    EbaySyncListingReportImport,
    EbaySyncRunCreate,
    EbaySyncRunProgress,
    EbaySyncRunRead,
    EbayRevisionEnqueueRequest,
    EbayRevisionCanaryRequest,
    EbayRevisionEnqueueResult,
    EbayRevisionJobRead,
    EbayRevisionJobUpdate,
    EbayRevisionSheetPrepareRequest,
    EbayRevisionSheetPrepareResult,
    EbayRevisionTemplateRead,
    EbayRevisionTemplateUpdate,
    EbayRevisionBatchRead,
    EbayRevisionBatchResultImport,
    EbayRevisionBatchUpdate,
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
    FinanceEntryImport,
    FinanceOverviewRead,
    FinancialAccountRead,
    FinancialAccountUpsert,
    GiftCardCreate,
    GiftCardCredentialStatus,
    GiftCardCredentialWrite,
    GiftCardRead,
    GiftCardUpdate,
    ListingQueueItem,
    ListingAutomationPauseStatus,
    ListingAutomationPauseUpdate,
    ListingJobCreate,
    ListingDraftVerification,
    ListingJobRead,
    ListingJobRunResult,
    ListingJobUpdate,
    ListingReadinessReport,
    OrderUpdateDraftRunRead,
    OrderRead,
    OperationalAlertRead,
    OperationalAlertSummary,
    OperationalAlertUpdate,
    PriceSnapshotRead,
    PricingSettingsUpdate,
    PushConfigRead,
    PushDispatchResult,
    PushSubscriptionCreate,
    PushSubscriptionRead,
    PushSubscriptionUpdate,
    PushSaleTestRequest,
    PushTestRequest,
    ProductImageDownloadResult,
    ProductImageOrderUpdate,
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
    SourceCaptureClaim,
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
    SupplierOptionRead,
    SupplierOrderPrepare,
    SupplierCheckoutCredentialRead,
    SupplierOrderClaimRead,
    SupplierOrderRead,
    SupplierOrderUpdate,
    SubscriptionExpenseCreate,
    SubscriptionExpenseRead,
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
    read_automation_pause,
    read_listing_job,
    serialize_listing_job,
    serialize_listing_job_lite,
    set_automation_pause,
    start_listing_job,
    start_next_listing_job,
    update_listing_job,
    verify_listing_job_draft,
)
from app.services.automation import create_repricing_snapshots, run_catalog_automation_cycle as run_catalog_cycle_service
from app.services.ebay import (
    complete_ebay_account_oauth,
    complete_ebay_oauth,
    ebay_connection_status,
    publish_ebay_sandbox_listing,
    refresh_ebay_access_token,
    refresh_ebay_account_access_token,
    start_ebay_account_oauth,
    start_ebay_oauth,
)
from app.services.ebay_traffic import import_traffic_file, import_traffic_report, sync_ebay_traffic, traffic_overview
from app.services.ebay_accounts import create_ebay_account, delete_ebay_account, list_ebay_accounts, update_ebay_account
from app.services.ebay_browser_account import read_ebay_browser_account_status, update_ebay_browser_account_status
from app.services.ebay_revisions import (
    approve_ebay_revision_job,
    create_ebay_revision_canary,
    enqueue_ebay_price_revisions,
    list_ebay_revision_jobs,
    serialize_ebay_revision_job,
    start_next_ebay_revision_job,
    update_ebay_revision_job,
)
from app.services.ebay_revision_csv import (
    build_ebay_price_revision_csv,
    read_ebay_revision_template,
    save_ebay_revision_template,
)
from app.services.ebay_revision_batches import (
    decode_ebay_revision_result,
    import_ebay_revision_result,
    list_ebay_revision_batches,
    prepare_next_ebay_revision_batch,
    serialize_ebay_revision_batch,
    update_ebay_revision_batch,
)
from app.services.ebay_sync import (
    claim_next_ebay_order_sync,
    claim_next_ebay_traffic_sync,
    capture_listing_views,
    import_listing_report_rows,
    list_ebay_sync_runs,
    claim_next_ebay_active_listing_sync,
    queue_ebay_order_sync,
    queue_ebay_traffic_sync,
    serialize_ebay_sync_run,
    start_ebay_sync_run,
    update_ebay_sync_run_progress,
)
from app.services.images import prepare_product_images_for_ebay
from app.services.monitoring import build_source_refresh_queue, run_source_monitoring_cycle
from app.services.orders import import_ebay_order_report_rows, parse_ebay_order_report, seed_mock_order
from app.services.order_updates import generate_order_update_drafts, list_customer_updates, update_customer_update_status
from app.services.customer_service import (
    claim_next_outbound_message,
    import_conversation,
    list_conversations,
    queue_message,
    queue_missing_order_thank_yous,
    queue_template_message,
    update_message,
)
from app.services.customer_templates import list_customer_templates, render_customer_template
from app.services.fulfillment import (
    approve_supplier_order,
    claim_next_supplier_order,
    create_gift_card,
    list_gift_cards,
    list_supplier_orders,
    prepare_supplier_order,
    update_gift_card,
    update_supplier_order,
)
from app.services.windows_credentials import (
    gift_card_credential_target,
    read_generic_credential,
    store_generic_credential,
)
from app.services.finance import (
    create_subscription,
    finance_overview,
    import_finance_entries,
    upsert_financial_account,
)
from app.services.z_finance import (
    build_orders as build_z_finance_orders,
    build_payouts as build_z_finance_payouts,
    build_summary as build_z_finance_summary,
    sync_from_z_finance,
)
from app.services.products import approve_candidate
from app.services.research import create_mock_candidates
from app.services.settings import read_pricing_settings, write_pricing_settings
from app.services.suppliers import supplier_catalog
from app.services.source_refresh_jobs import (
    claim_next_source_refresh_job_any_batch,
    claim_next_source_refresh_job,
    create_automatic_source_refresh_batch,
    complete_source_refresh_job,
    create_source_refresh_batch,
    fail_source_refresh_job,
    list_source_refresh_jobs,
    reject_suspicious_source_refresh_price,
    serialize_source_refresh_job,
    source_refresh_has_running_job,
)
from app.services.workers import heartbeat_current_worker, list_workers, read_current_worker
from app.services.alerts import list_operational_alerts, summarize_operational_alerts, update_operational_alert_status
from app.services.push_notifications import (
    dispatch_alert_notifications,
    get_push_config,
    list_push_subscriptions,
    send_latest_order_sale_test,
    serialize_push_subscription,
    send_test_push,
    update_push_subscription,
    upsert_push_subscription,
)

router = APIRouter()


def _require_z_finance_bearer(request: Request) -> None:
    configured = get_settings().autozs_z_finance_token
    if not configured:
        raise HTTPException(status_code=503, detail="Z Finance integration is not configured")
    authorization = request.headers.get("Authorization", "")
    supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not supplied or not hmac.compare_digest(supplied, configured):
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/browser-recovery/home-depot-backup")
def launch_home_depot_backup_profile() -> dict[str, str]:
    chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    extension_source = Path(r"C:\AutoZS\repo\tools\chrome-extension")
    extension = Path(r"C:\AutoZS\chrome-extensions\home-depot-backup")
    profile = Path(r"C:\AutoZS\chrome-profiles\home-depot-backup-capture-only")
    if not chrome.exists():
        raise HTTPException(status_code=503, detail="Chrome is not installed at the configured Windows path")
    if not (extension_source / "manifest.json").exists():
        raise HTTPException(status_code=503, detail="The AutoZS Chrome extension is unavailable")
    extension.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(extension_source, extension, dirs_exist_ok=True)
    manifest_path = extension / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["name"] = "AutoZS Home Depot Backup Capture"
    manifest["description"] = "Capture-only Home Depot failover worker. This extension cannot run eBay jobs."
    manifest["host_permissions"] = [
        permission
        for permission in manifest.get("host_permissions", [])
        if "homedepot.com" in permission
        or "desktop-56u49jf" in permission
        or "127.0.0.1" in permission
        or "localhost" in permission
    ]
    manifest["content_scripts"] = [
        script
        for script in manifest.get("content_scripts", [])
        if not any("ebay.com" in match for match in script.get("matches", []))
        and not any("lowes.com" in match for match in script.get("matches", []))
    ]
    for resource in manifest.get("web_accessible_resources", []):
        resource["matches"] = [match for match in resource.get("matches", []) if "homedepot.com" in match]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    profile.mkdir(parents=True, exist_ok=True)
    dashboard = (
        "https://desktop-56u49jf.tailb2892a.ts.net/"
        "?api=https://desktop-56u49jf.tailb2892a.ts.net:8443"
        "&autozs_worker_mode=capture"
    )
    subprocess.Popen(
        [
            str(chrome),
            f"--user-data-dir={profile}",
            "--profile-directory=Default",
            f"--load-extension={extension}",
            "--no-first-run",
            "--no-default-browser-check",
            dashboard,
        ],
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return {"status": "launched", "profile": str(profile), "mode": "capture"}


def _require_local_checkout_request(request: Request) -> None:
    host = str(request.client.host if request.client else "")
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Checkout credentials are only available to the local Windows worker.")


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


@router.get("/alerts", response_model=list[OperationalAlertRead])
def read_operational_alerts(
    status: str = Query("active", pattern="^(active|open|acknowledged|resolved|dismissed|all)$"),
    limit: int = Query(100, ge=1, le=250),
    db: Session = Depends(get_db),
) -> list[OperationalAlertRead]:
    return list_operational_alerts(db, status=status, limit=limit)


@router.get("/alerts/summary", response_model=OperationalAlertSummary)
def read_operational_alert_summary(db: Session = Depends(get_db)) -> OperationalAlertSummary:
    return OperationalAlertSummary(**summarize_operational_alerts(db))


@router.patch("/alerts/{alert_id}", response_model=OperationalAlertRead)
def patch_operational_alert(
    alert_id: int,
    payload: OperationalAlertUpdate,
    db: Session = Depends(get_db),
) -> OperationalAlertRead:
    alert = update_operational_alert_status(db, alert_id, payload.status)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.get("/push/config", response_model=PushConfigRead)
def read_push_config_route() -> PushConfigRead:
    return PushConfigRead(**get_push_config())


@router.get("/push/subscriptions", response_model=list[PushSubscriptionRead])
def read_push_subscriptions_route(db: Session = Depends(get_db)) -> list[PushSubscriptionRead]:
    return [PushSubscriptionRead(**serialize_push_subscription(subscription)) for subscription in list_push_subscriptions(db)]


@router.post("/push/subscriptions", response_model=PushSubscriptionRead)
def create_push_subscription_route(
    payload: PushSubscriptionCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> PushSubscriptionRead:
    keys = payload.keys or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if not payload.endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Push subscription endpoint and keys are required")
    subscription = upsert_push_subscription(
        db,
        endpoint=payload.endpoint,
        p256dh=p256dh,
        auth=auth,
        label=payload.label or "AutoZS iPhone",
        user_agent=payload.user_agent or request.headers.get("user-agent", ""),
        dashboard_url=payload.dashboard_url or "",
        vapid_public_key=payload.vapid_public_key or "",
        preferences=payload.preferences,
    )
    return PushSubscriptionRead(**serialize_push_subscription(subscription))


@router.patch("/push/subscriptions/{subscription_id}", response_model=PushSubscriptionRead)
def patch_push_subscription_route(
    subscription_id: int,
    payload: PushSubscriptionUpdate,
    db: Session = Depends(get_db),
) -> PushSubscriptionRead:
    subscription = db.get(PushSubscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Push subscription not found")
    updated = update_push_subscription(
        db,
        subscription,
        enabled=payload.enabled,
        preferences=payload.preferences,
        timezone_name=payload.timezone,
        weekly_summary_day=payload.weekly_summary_day,
        weekly_summary_time=payload.weekly_summary_time,
        weekly_summary_enabled=payload.weekly_summary_enabled,
    )
    return PushSubscriptionRead(**serialize_push_subscription(updated))


@router.post("/push/test", response_model=PushDispatchResult)
def send_push_test_route(payload: PushTestRequest, db: Session = Depends(get_db)) -> PushDispatchResult:
    return PushDispatchResult(**send_test_push(
        db,
        title=payload.title,
        body=payload.body,
        subscription_id=payload.subscription_id,
    ))


@router.post("/push/test-sale", response_model=PushDispatchResult)
def send_push_sale_test_route(payload: PushSaleTestRequest, db: Session = Depends(get_db)) -> PushDispatchResult:
    return PushDispatchResult(**send_latest_order_sale_test(
        db,
        subscription_id=payload.subscription_id,
    ))


@router.post("/push/dispatch-alerts", response_model=PushDispatchResult)
def dispatch_push_alerts_route(db: Session = Depends(get_db)) -> PushDispatchResult:
    return PushDispatchResult(**dispatch_alert_notifications(db))


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


@router.post("/ebay/accounts/{account_key}/oauth/start", response_model=EbayOAuthStartRead)
def start_ebay_account_oauth_flow(account_key: str, db: Session = Depends(get_db)) -> EbayOAuthStartRead:
    try:
        result = start_ebay_account_oauth(db, account_key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if result.get("missing"):
        raise HTTPException(status_code=400, detail={"missing": result["missing"]})
    return EbayOAuthStartRead(**result)


@router.post("/ebay/accounts/{account_key}/oauth/callback", response_model=EbayOAuthTokenRead)
def complete_ebay_account_oauth_flow(
    account_key: str,
    payload: EbayOAuthCallbackRequest,
    db: Session = Depends(get_db),
) -> EbayOAuthTokenRead:
    try:
        result = complete_ebay_account_oauth(db, account_key, payload.code, payload.state)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EbayOAuthTokenRead(**result)


@router.post("/ebay/accounts/{account_key}/oauth/refresh", response_model=EbayOAuthTokenRead)
def refresh_ebay_account_oauth_token(account_key: str, db: Session = Depends(get_db)) -> EbayOAuthTokenRead:
    try:
        result = refresh_ebay_account_access_token(db, account_key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EbayOAuthTokenRead(**result)


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


def _depop_variant_read(variant: DepopListingVariant) -> DepopVariantRead:
    try:
        image_ids = [int(value) for value in json.loads(variant.image_ids_json or "[]")]
    except (TypeError, ValueError, json.JSONDecodeError):
        image_ids = []
    return DepopVariantRead(
        id=variant.id,
        product_id=variant.product_id,
        account_key=variant.account_key,
        variant_key=variant.variant_key,
        title=variant.title,
        description=variant.description,
        price=variant.price,
        image_ids=image_ids,
        size=variant.size,
        brand=variant.brand,
        category=variant.category,
        condition=variant.condition,
        color=variant.color,
        status=variant.status,
        depop_listing_id=variant.depop_listing_id,
        published_at=variant.published_at,
        created_at=variant.created_at,
        updated_at=variant.updated_at,
    )


@router.get("/depop/accounts", response_model=list[DepopAccountRead])
def list_depop_accounts(db: Session = Depends(get_db)) -> list[DepopAccount]:
    return list(db.scalars(select(DepopAccount).order_by(DepopAccount.label)).all())


@router.post("/depop/accounts", response_model=DepopAccountRead)
def upsert_depop_account(payload: DepopAccountUpsert, db: Session = Depends(get_db)) -> DepopAccount:
    account = db.scalar(select(DepopAccount).where(DepopAccount.key == payload.key))
    if account is None:
        account = DepopAccount(key=payload.key, label=payload.label)
        db.add(account)
    for field, value in payload.model_dump().items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return account


def _depop_variant_key(variation: object, index: int) -> str:
    asin = str(getattr(variation, "asin", "") or "").strip()
    if asin:
        return asin
    label = str(getattr(variation, "label", "") or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", label).strip("-")
    return slug or f"variation-{index + 1}"


def _resolve_depop_account_key(db: Session, requested: str) -> str:
    if requested:
        return requested
    account = db.scalar(
        select(DepopAccount).where(DepopAccount.enabled.is_(True)).order_by(DepopAccount.id)
    )
    return account.key if account is not None else ""


@router.post("/depop/amazon-import", response_model=DepopImportResult)
def import_amazon_capture(payload: AmazonCaptureImport, db: Session = Depends(get_db)) -> DepopImportResult:
    """Turn one scraped Amazon parent listing into Depop variants + swipe candidates.

    Deliberately tolerant: it runs before a Depop account exists so capture is
    never blocked on account setup, and re-importing the same listing is a no-op
    for anything already stored.
    """
    product = db.get(Product, payload.product_id)
    if product is None or product.status == ProductStatus.deleted.value:
        raise HTTPException(status_code=404, detail="Product not found")

    account_key = _resolve_depop_account_key(db, payload.account_key)
    base_title = (payload.title or product.title or "").strip()

    variants_created = 0
    variants_existing = 0
    variant_by_label: dict[str, DepopListingVariant] = {}
    for index, variation in enumerate(payload.variations):
        variant_key = _depop_variant_key(variation, index)
        variant = db.scalar(
            select(DepopListingVariant).where(
                DepopListingVariant.product_id == product.id,
                DepopListingVariant.variant_key == variant_key,
            )
        )
        if variant is None:
            variant = DepopListingVariant(
                product_id=product.id,
                account_key=account_key,
                variant_key=variant_key,
                title=f"{base_title} - {variation.label}".strip(" -")[:512] or variation.label,
                description="",
                price=0.0,
                image_ids_json="[]",
                color=variation.label[:64],
                status="draft",
            )
            db.add(variant)
            db.flush()
            variants_created += 1
        else:
            variants_existing += 1
        variant_by_label[variation.label.strip().lower()] = variant

    # Resolve colours against every variant this product has, not just the ones
    # in this payload -- a photo-only re-import still has to match the variants
    # stored on a previous pass.
    for variant in db.scalars(
        select(DepopListingVariant).where(DepopListingVariant.product_id == product.id)
    ).all():
        label = (variant.color or "").strip().lower()
        if label:
            variant_by_label.setdefault(label, variant)

    photos_created = 0
    photos_skipped = 0

    def _add_photo(
        *,
        image_url: str,
        thumb_url: str,
        kind: str,
        variant_label: str = "",
        source_asin: str = "",
        review_id: str = "",
        variant_id: int | None = None,
        width: int = 0,
        height: int = 0,
        sort_order: int = 0,
    ) -> None:
        nonlocal photos_created, photos_skipped
        url = (image_url or "").strip()
        if not url:
            photos_skipped += 1
            return
        existing = db.scalar(
            select(DepopSourcePhoto).where(
                DepopSourcePhoto.product_id == product.id,
                DepopSourcePhoto.image_url == url,
            )
        )
        if existing is not None:
            photos_skipped += 1
            return
        db.add(
            DepopSourcePhoto(
                product_id=product.id,
                kind=kind,
                image_url=url,
                thumb_url=(thumb_url or "").strip(),
                review_id=review_id[:32],
                source_asin=source_asin[:32],
                variant_label=variant_label[:128],
                variant_id=variant_id,
                status="pending",
                width=width,
                height=height,
                sort_order=sort_order,
            )
        )
        photos_created += 1

    for index, variation in enumerate(payload.variations):
        variant = variant_by_label.get(variation.label.strip().lower())
        _add_photo(
            image_url=variation.image_url,
            thumb_url=variation.thumb_url,
            kind="variation",
            variant_label=variation.label,
            source_asin=variation.asin,
            variant_id=variant.id if variant is not None else None,
            sort_order=index,
        )

    # A review photo can often be attributed automatically: its data-reviewid
    # points at a review body that names the colour. Only data-reviewid is
    # trustworthy here -- the carousel's data-asin reports whichever variation
    # the page was showing, not the one the reviewer bought. A resolved match is
    # stored as a suggestion (status stays pending) so it can be overridden.
    review_colors = {
        str(key).strip(): str(value).strip()
        for key, value in payload.review_colors.items()
        if str(key).strip() and str(value).strip()
    }
    suggested = 0
    for index, photo in enumerate(payload.review_photos):
        label = review_colors.get(photo.review_id.strip(), "") if photo.review_id else ""
        variant = variant_by_label.get(label.lower()) if label else None
        if variant is not None:
            suggested += 1
        _add_photo(
            image_url=photo.image_url,
            thumb_url=photo.thumb_url,
            kind="review",
            review_id=photo.review_id,
            variant_label=label,
            variant_id=variant.id if variant is not None else None,
            width=photo.width,
            height=photo.height,
            sort_order=index,
        )

    db.commit()

    variants = list(
        db.scalars(
            select(DepopListingVariant)
            .where(DepopListingVariant.product_id == product.id)
            .order_by(DepopListingVariant.id)
        ).all()
    )
    photos = list(
        db.scalars(
            select(DepopSourcePhoto)
            .where(DepopSourcePhoto.product_id == product.id)
            .order_by(DepopSourcePhoto.kind, DepopSourcePhoto.sort_order, DepopSourcePhoto.id)
        ).all()
    )
    return DepopImportResult(
        product_id=product.id,
        variants_created=variants_created,
        variants_existing=variants_existing,
        photos_created=photos_created,
        photos_skipped=photos_skipped,
        variants=[_depop_variant_read(item) for item in variants],
        photos=[DepopSourcePhotoRead.model_validate(item) for item in photos],
    )


@router.get("/depop/photo-queue", response_model=list[DepopPhotoQueueItem])
def list_depop_photo_queue(db: Session = Depends(get_db)) -> list[DepopPhotoQueueItem]:
    """Products that have captured photos, newest first, with review progress."""
    photos = list(
        db.scalars(
            select(DepopSourcePhoto).order_by(DepopSourcePhoto.product_id, DepopSourcePhoto.id)
        ).all()
    )
    if not photos:
        return []
    product_ids = {photo.product_id for photo in photos}
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_(product_ids))).all()
    }
    variant_counts: dict[int, int] = {}
    for variant in db.scalars(
        select(DepopListingVariant).where(DepopListingVariant.product_id.in_(product_ids))
    ).all():
        variant_counts[variant.product_id] = variant_counts.get(variant.product_id, 0) + 1

    grouped: dict[int, dict[str, object]] = {}
    for photo in photos:
        entry = grouped.setdefault(
            photo.product_id,
            {"pending": 0, "approved": 0, "rejected": 0, "cover": ""},
        )
        if photo.status in ("pending", "approved", "rejected"):
            entry[photo.status] = int(entry[photo.status]) + 1
        if not entry["cover"] and photo.kind == "variation":
            entry["cover"] = photo.image_url

    items: list[DepopPhotoQueueItem] = []
    for product_id, entry in grouped.items():
        product = products.get(product_id)
        if product is None or product.status == ProductStatus.deleted.value:
            continue
        items.append(
            DepopPhotoQueueItem(
                product_id=product_id,
                product_title=product.title,
                variants=variant_counts.get(product_id, 0),
                pending=int(entry["pending"]),
                approved=int(entry["approved"]),
                rejected=int(entry["rejected"]),
                cover_image=str(entry["cover"]),
            )
        )
    # Anything still needing review floats to the top.
    items.sort(key=lambda item: (item.pending == 0, -item.product_id))
    return items


@router.get("/depop/photo-review/{product_id}", response_model=DepopPhotoReviewRead)
def read_depop_photo_review(product_id: int, db: Session = Depends(get_db)) -> DepopPhotoReviewRead:
    product = db.get(Product, product_id)
    if product is None or product.status == ProductStatus.deleted.value:
        raise HTTPException(status_code=404, detail="Product not found")
    variants = list(
        db.scalars(
            select(DepopListingVariant)
            .where(DepopListingVariant.product_id == product_id)
            .order_by(DepopListingVariant.id)
        ).all()
    )
    photos = list(
        db.scalars(
            select(DepopSourcePhoto)
            .where(DepopSourcePhoto.product_id == product_id)
            .order_by(DepopSourcePhoto.kind, DepopSourcePhoto.sort_order, DepopSourcePhoto.id)
        ).all()
    )
    return DepopPhotoReviewRead(
        product_id=product_id,
        product_title=product.title,
        variants=[_depop_variant_read(item) for item in variants],
        photos=[DepopSourcePhotoRead.model_validate(item) for item in photos],
    )


@router.get("/depop/source-photos", response_model=list[DepopSourcePhotoRead])
def list_depop_source_photos(
    product_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[DepopSourcePhoto]:
    stmt = select(DepopSourcePhoto).order_by(
        DepopSourcePhoto.kind, DepopSourcePhoto.sort_order, DepopSourcePhoto.id
    )
    if product_id is not None:
        stmt = stmt.where(DepopSourcePhoto.product_id == product_id)
    if status:
        stmt = stmt.where(DepopSourcePhoto.status == status)
    if kind:
        stmt = stmt.where(DepopSourcePhoto.kind == kind)
    return list(db.scalars(stmt).all())


@router.post("/depop/source-photos/{photo_id}/decision", response_model=DepopSourcePhotoRead)
def decide_depop_source_photo(
    photo_id: int, payload: DepopPhotoDecision, db: Session = Depends(get_db)
) -> DepopSourcePhoto:
    """Record a swipe. Approving with a variant also wires the photo into that
    variant's publish payload, so the swipe queue feeds the existing Depop
    listing path instead of being a parallel store."""
    photo = db.get(DepopSourcePhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    variant: DepopListingVariant | None = None
    if payload.variant_id is not None:
        variant = db.get(DepopListingVariant, payload.variant_id)
        if variant is None or variant.product_id != photo.product_id:
            raise HTTPException(status_code=400, detail="Variant must belong to the same product")

    photo.status = payload.status
    photo.variant_id = variant.id if variant is not None else None
    if variant is not None:
        photo.variant_label = variant.color or photo.variant_label

    if payload.status == "approved" and variant is not None:
        image = db.scalar(
            select(ProductImage).where(
                ProductImage.product_id == photo.product_id,
                ProductImage.image_url == photo.image_url,
            )
        )
        if image is None:
            highest = db.scalar(
                select(func.max(ProductImage.sort_order)).where(
                    ProductImage.product_id == photo.product_id
                )
            )
            image = ProductImage(
                product_id=photo.product_id,
                image_url=photo.image_url,
                sort_order=int(highest or 0) + 1,
            )
            db.add(image)
            db.flush()
        try:
            image_ids = [int(value) for value in json.loads(variant.image_ids_json or "[]")]
        except (TypeError, ValueError, json.JSONDecodeError):
            image_ids = []
        if image.id not in image_ids and len(image_ids) < 4:
            image_ids.append(image.id)
            variant.image_ids_json = json.dumps(image_ids)

    db.commit()
    db.refresh(photo)
    return photo


@router.get("/depop/variants", response_model=list[DepopVariantRead])
def list_depop_variants(
    product_id: int | None = Query(default=None),
    account_key: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[DepopVariantRead]:
    stmt = select(DepopListingVariant).order_by(DepopListingVariant.created_at.desc())
    if product_id is not None:
        stmt = stmt.where(DepopListingVariant.product_id == product_id)
    if account_key:
        stmt = stmt.where(DepopListingVariant.account_key == account_key)
    return [_depop_variant_read(item) for item in db.scalars(stmt).all()]


@router.post("/depop/variants", response_model=DepopVariantRead)
def create_depop_variant(payload: DepopVariantCreate, db: Session = Depends(get_db)) -> DepopVariantRead:
    product = db.get(Product, payload.product_id)
    if product is None or product.status == ProductStatus.deleted.value:
        raise HTTPException(status_code=404, detail="Product not found")
    account = db.scalar(select(DepopAccount).where(DepopAccount.key == payload.account_key))
    if account is None or not account.enabled:
        raise HTTPException(status_code=400, detail="Select an enabled Depop account")
    image_ids = list(dict.fromkeys(payload.image_ids))
    if image_ids:
        owned = set(
            db.scalars(
                select(ProductImage.id).where(
                    ProductImage.product_id == product.id, ProductImage.id.in_(image_ids)
                )
            ).all()
        )
        if owned != set(image_ids):
            raise HTTPException(status_code=400, detail="Every image must belong to this product")
    existing = db.scalar(
        select(DepopListingVariant).where(
            DepopListingVariant.product_id == product.id,
            DepopListingVariant.variant_key == payload.variant_key,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="This product already has that Depop variant")
    variant = DepopListingVariant(
        product_id=product.id,
        account_key=payload.account_key,
        variant_key=payload.variant_key,
        title=payload.title,
        description=payload.description,
        price=payload.price,
        image_ids_json=json.dumps(image_ids),
        size=payload.size,
        brand=payload.brand,
        category=payload.category,
        condition=payload.condition,
        color=payload.color,
        status="ready" if 3 <= len(image_ids) <= 4 else "draft",
    )
    db.add(variant)
    if not any(draft.marketplace == "depop" for draft in product.listing_drafts):
        product.listing_drafts.append(
            ListingDraft(
                marketplace="depop",
                title=payload.title,
                description=payload.description,
                calculated_price=payload.price,
                status="draft",
            )
        )
    db.commit()
    db.refresh(variant)
    return _depop_variant_read(variant)


@router.patch("/depop/variants/{variant_id}", response_model=DepopVariantRead)
def update_depop_variant(
    variant_id: int, payload: DepopVariantUpdate, db: Session = Depends(get_db)
) -> DepopVariantRead:
    variant = db.get(DepopListingVariant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Depop variant not found")
    changes = payload.model_dump(exclude_unset=True)
    image_ids = changes.pop("image_ids", None)
    if image_ids is not None:
        image_ids = list(dict.fromkeys(image_ids))
        owned = set(
            db.scalars(
                select(ProductImage.id).where(
                    ProductImage.product_id == variant.product_id, ProductImage.id.in_(image_ids)
                )
            ).all()
        )
        if owned != set(image_ids):
            raise HTTPException(status_code=400, detail="Every image must belong to this product")
        variant.image_ids_json = json.dumps(image_ids)
    for field, value in changes.items():
        setattr(variant, field, value)
    if "status" not in changes:
        count = len(json.loads(variant.image_ids_json or "[]"))
        variant.status = "ready" if 3 <= count <= 4 else "draft"
    db.commit()
    db.refresh(variant)
    return _depop_variant_read(variant)


@router.get("/depop/jobs", response_model=list[DepopJobRead])
def list_depop_jobs(db: Session = Depends(get_db)) -> list[DepopListingJob]:
    return list(db.scalars(select(DepopListingJob).order_by(DepopListingJob.created_at.desc())).all())


@router.post("/depop/jobs", response_model=DepopJobRead)
def enqueue_depop_job(payload: DepopJobCreate, db: Session = Depends(get_db)) -> DepopListingJob:
    variant = db.get(DepopListingVariant, payload.variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Depop variant not found")
    account = db.scalar(select(DepopAccount).where(DepopAccount.key == variant.account_key))
    if account is None or not account.enabled:
        raise HTTPException(status_code=400, detail="Depop account is unavailable")
    if not account.writes_enabled:
        raise HTTPException(status_code=409, detail="Enable Depop browser writes before queueing")
    image_count = len(json.loads(variant.image_ids_json or "[]"))
    if image_count < 3 or image_count > 4:
        raise HTTPException(status_code=400, detail="Depop variants require 3 or 4 original images")
    existing = db.scalar(
        select(DepopListingJob).where(
            DepopListingJob.variant_id == variant.id,
            DepopListingJob.status.in_(["queued", "running"]),
        )
    )
    if existing is not None:
        return existing
    job = DepopListingJob(
        variant_id=variant.id,
        account_key=variant.account_key,
        action=payload.action,
        status="queued",
        scheduled_for=payload.scheduled_for,
        message="Waiting for the dedicated Depop Chrome profile.",
    )
    variant.status = "queued"
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.patch("/depop/jobs/{job_id}", response_model=DepopJobRead)
def update_depop_job(
    job_id: int, payload: DepopJobUpdate, db: Session = Depends(get_db)
) -> DepopListingJob:
    job = db.get(DepopListingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Depop job not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return job


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


@router.get("/suppliers", response_model=list[SupplierOptionRead])
def list_supplier_options() -> list[SupplierOptionRead]:
    return [SupplierOptionRead(**item) for item in supplier_catalog()]


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
    reject_home_depot_error_capture(payload.source_url, payload.title)
    reject_bulk_source_capture(
        db,
        source_url=payload.source_url,
        source_bulk_package=payload.source_bulk_package,
        source_purchase_unit=payload.source_purchase_unit,
        reason=payload.source_bulk_package_reason,
        refresh_job_id=payload.refresh_job_id,
    )
    if payload.refresh_job_id:
        job = db.get(SourceRefreshJob, payload.refresh_job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Source refresh job not found")
        suspicious_price = reject_suspicious_source_refresh_price(db, payload.refresh_job_id, payload.source_price)
        if suspicious_price:
            raise HTTPException(status_code=422, detail=suspicious_price)
        missing_capture_fields: list[str] = []
        if not payload.title.strip():
            missing_capture_fields.append("title")
        if not split_urls(payload.image_urls or ""):
            missing_capture_fields.append("images")
        if missing_capture_fields:
            message = (
                "Incomplete automatic source capture; preserved the existing product data. "
                f"Missing {', '.join(missing_capture_fields)}."
            )
            fail_source_refresh_job(db, payload.refresh_job_id, message)
            raise HTTPException(status_code=422, detail=message)
        product = update_product_from_capture(
            db,
            product_id=job.product_id,
            source_price=payload.source_price,
            source_shipping=payload.source_shipping,
            source_in_stock=payload.source_in_stock,
            source_price_unavailable=payload.source_price_unavailable,
            subscription_discount_percent=payload.subscription_discount_percent,
            minimum_order_quantity=payload.minimum_order_quantity,
        )
        if product is None:
            raise HTTPException(status_code=404, detail="Source refresh product not found")
        complete_source_refresh_job(db, payload.refresh_job_id, product.id)
        return product
    product = import_captured_product(
        db,
        source_url=payload.source_url,
        title=payload.title,
        source_price=payload.source_price,
        source_shipping=payload.source_shipping,
        source_in_stock=payload.source_in_stock,
        source_price_unavailable=payload.source_price_unavailable,
        competitor_price=payload.competitor_price,
        subscription_discount_percent=payload.subscription_discount_percent,
        minimum_order_quantity=payload.minimum_order_quantity,
        description=payload.description,
        image_urls=payload.image_urls,
    )
    product.capture_lease_owner = None
    product.capture_lease_expires_at = None
    db.commit()
    db.refresh(product)
    enqueue_ebay_price_revisions(db, product_ids=[product.id])
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
        # An unavailable source intentionally has no shipping quote. Keeping it
        # in the capture queue would reopen the same page forever while waiting
        # for shipping data that cannot exist.
        if supplier.in_stock is False or supplier.price_unavailable:
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


@router.post("/products/capture-queue/claim", response_model=SourceCaptureQueueItem | None)
def claim_source_capture_item(
    payload: SourceCaptureClaim,
    db: Session = Depends(get_db),
) -> SourceCaptureQueueItem | None:
    now = datetime.utcnow()
    lease_expires_at = now + timedelta(minutes=20)
    # Build the eligible queue with the same rules used by the dashboard, then
    # atomically claim the first row whose prior lease is absent or expired.
    # The conditional UPDATE prevents two Chrome profiles from owning the same
    # product even when their polling requests arrive together.
    for item in source_capture_queue(db).items:
        if payload.source_host and payload.source_host.lower() not in item.source_url.lower():
            continue
        claimed = db.execute(
            update(Product)
            .where(
                Product.id == item.product_id,
                or_(
                    Product.capture_lease_expires_at.is_(None),
                    Product.capture_lease_expires_at <= now,
                    Product.capture_lease_owner == payload.worker_id,
                ),
            )
            .values(
                capture_lease_owner=payload.worker_id,
                capture_lease_expires_at=lease_expires_at,
            )
        )
        db.commit()
        if claimed.rowcount:
            return item
    return None


@router.patch("/products/{product_id}/capture", response_model=ProductRead)
def update_product_capture(product_id: int, payload: CapturedProductUpdate, db: Session = Depends(get_db)) -> Product:
    product_before_update = db.get(Product, product_id)
    if product_before_update is not None and product_before_update.supplier_products:
        source_url = product_before_update.supplier_products[0].source_url
        reject_home_depot_error_capture(source_url, payload.title)
        reject_bulk_source_capture(
            db,
            source_url=source_url,
            source_bulk_package=payload.source_bulk_package,
            source_purchase_unit=payload.source_purchase_unit,
            reason=payload.source_bulk_package_reason,
            product_id=product_id,
        )
    product = update_product_from_capture(
        db,
        product_id=product_id,
        title=payload.title,
        source_price=payload.source_price,
        source_shipping=payload.source_shipping,
        source_in_stock=payload.source_in_stock,
        source_price_unavailable=payload.source_price_unavailable,
        competitor_price=payload.competitor_price,
        subscription_discount_percent=payload.subscription_discount_percent,
        minimum_order_quantity=payload.minimum_order_quantity,
        description=payload.description,
        image_urls=payload.image_urls,
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    enqueue_ebay_price_revisions(db, product_ids=[product.id])
    return product


def reject_home_depot_error_capture(source_url: str | None, title: str | None) -> None:
    if not source_url or not title:
        return
    if "homedepot.com" in source_url.lower() and title.strip().lower() == "error page":
        raise HTTPException(status_code=422, detail="Home Depot returned an error page; refresh the source page and try again")


def reject_bulk_source_capture(
    db: Session,
    *,
    source_url: str | None,
    source_bulk_package: bool,
    source_purchase_unit: str | None,
    reason: str | None,
    refresh_job_id: int | None = None,
    product_id: int | None = None,
) -> None:
    if not source_bulk_package:
        return
    unit = (source_purchase_unit or "bulk package").strip().lower()
    if source_url and "homedepot.com" not in source_url.lower():
        return
    message = (
        f"Excluded bulk-source product ({unit}); AutoZS does not import case, carton, pallet, "
        "or coverage-priced products as single items."
    )
    if reason:
        message = f"{message} {reason.strip()}"
    if refresh_job_id:
        refresh_job = db.get(SourceRefreshJob, refresh_job_id)
        if refresh_job is not None:
            product_id = refresh_job.product_id
    if product_id:
        product = db.get(Product, product_id)
        if product is not None:
            product.status = ProductStatus.paused.value
            db.commit()
    if refresh_job_id:
        fail_source_refresh_job(db, refresh_job_id, message)
    raise HTTPException(status_code=422, detail=message)


@router.patch("/products/{product_id}/listing-schedule", response_model=ProductRead)
def update_product_listing_schedule(
    product_id: int, payload: ProductListingScheduleUpdate, db: Session = Depends(get_db)
) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    schedule = payload.listing_schedule_at
    product.listing_schedule_at = schedule.astimezone(timezone.utc).replace(tzinfo=None) if schedule and schedule.tzinfo else schedule
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
    product.capture_lease_owner = None
    product.capture_lease_expires_at = None
    db.commit()
    db.refresh(product)
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


@router.patch("/products/{product_id}/images/order", response_model=ProductRead)
def reorder_product_images(product_id: int, payload: ProductImageOrderUpdate, db: Session = Depends(get_db)) -> Product:
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id == product_id)
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    current_ids = {image.id for image in product.images}
    requested_ids = payload.image_ids
    if len(requested_ids) != len(set(requested_ids)) or set(requested_ids) != current_ids:
        raise HTTPException(status_code=400, detail="Image order must include every product image exactly once")
    images_by_id = {image.id: image for image in product.images}
    for sort_order, image_id in enumerate(requested_ids):
        images_by_id[image_id].sort_order = sort_order
    db.commit()
    return db.scalar(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id == product_id)
    )


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


@router.get("/ebay/listings/{listing_id}/view-history", response_model=list[EbayListingViewSnapshotRead])
def read_ebay_listing_view_history(
    listing_id: int,
    limit: int = Query(90, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[EbayListingViewSnapshotRead]:
    listing = db.get(EbayListing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="eBay listing not found")
    snapshots = db.scalars(
        select(EbayListingViewSnapshot)
        .where(EbayListingViewSnapshot.ebay_listing_id == listing_id)
        .order_by(EbayListingViewSnapshot.captured_at.desc(), EbayListingViewSnapshot.id.desc())
        .limit(limit)
    ).all()
    return [EbayListingViewSnapshotRead.model_validate(item) for item in snapshots]


@router.get("/ebay/listing-views/summary", response_model=EbayListingViewsSummary)
def read_ebay_listing_views_summary(
    account_key: str | None = None,
    db: Session = Depends(get_db),
) -> EbayListingViewsSummary:
    listing_stmt = select(EbayListing).where(
        EbayListing.status.in_({"active", "live", "listed", "scheduled"})
    )
    if account_key:
        listing_stmt = listing_stmt.where(EbayListing.account_id == account_key)
    listings = list(db.scalars(listing_stmt).all())
    listing_ids = [listing.id for listing in listings]
    if not listing_ids:
        return EbayListingViewsSummary(account_key=account_key)

    cutoff = datetime.utcnow() - timedelta(days=7)
    snapshots = list(
        db.scalars(
            select(EbayListingViewSnapshot)
            .where(
                EbayListingViewSnapshot.ebay_listing_id.in_(listing_ids),
                EbayListingViewSnapshot.captured_at >= cutoff,
            )
            .order_by(
                EbayListingViewSnapshot.ebay_listing_id,
                EbayListingViewSnapshot.captured_at,
                EbayListingViewSnapshot.id,
            )
        ).all()
    )
    snapshots_by_listing: dict[int, list[EbayListingViewSnapshot]] = {}
    for snapshot in snapshots:
        snapshots_by_listing.setdefault(snapshot.ebay_listing_id, []).append(snapshot)

    views_7d = 0
    for listing in listings:
        history = snapshots_by_listing.get(listing.id, [])
        if len(history) > 1:
            views_7d += sum(max(0, current.views - previous.views) for previous, current in zip(history, history[1:]))
        elif history:
            tracking_start = listing.started_at or listing.created_at
            if tracking_start and tracking_start >= cutoff:
                views_7d += max(0, history[0].views)

    measured = [listing for listing in listings if listing.views_measured_at is not None]
    measured_at = max((listing.views_measured_at for listing in measured), default=None)
    return EbayListingViewsSummary(
        account_key=account_key,
        views_30d=sum(max(0, listing.views or 0) for listing in listings),
        views_7d=views_7d,
        listings_measured=len(measured),
        measured_at=measured_at,
    )


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
        "view_delta": listing.view_delta,
        "views_measured_at": listing.views_measured_at,
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
        "listing_view_delta": listing.view_delta,
        "listing_views_measured_at": listing.views_measured_at,
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
    run = start_ebay_sync_run(
        db,
        account_key=payload.account_key,
        source=payload.source,
        report_type=payload.report_type,
    )
    return EbaySyncRunRead(**serialize_ebay_sync_run(run))


@router.post("/ebay/sync-runs/active-listings/next", response_model=EbaySyncRunRead | None)
def claim_ebay_active_listing_sync_run(
    account_key: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db),
) -> EbaySyncRunRead | None:
    run = claim_next_ebay_active_listing_sync(db, account_key=account_key)
    return EbaySyncRunRead(**serialize_ebay_sync_run(run)) if run else None


@router.post("/ebay/sync-runs/traffic/next", response_model=EbaySyncRunRead | None)
def claim_ebay_traffic_sync_run(
    account_key: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db),
) -> EbaySyncRunRead | None:
    run = claim_next_ebay_traffic_sync(db, account_key=account_key)
    return EbaySyncRunRead(**serialize_ebay_sync_run(run)) if run else None


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


@router.post("/ebay/sync-runs/listing-views", response_model=EbayListingViewsCaptureResult)
def import_ebay_listing_views(
    payload: EbayListingViewsCapture,
    db: Session = Depends(get_db),
) -> EbayListingViewsCaptureResult:
    captured, unmatched = capture_listing_views(
        db,
        rows=[row.model_dump(exclude_none=True) for row in payload.rows],
        account_key=payload.account_key,
        run_id=payload.run_id,
    )
    return EbayListingViewsCaptureResult(captured=captured, unmatched=unmatched)


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
    limit: int = Query(100, ge=1, le=1000),
    lite: bool = False,
    db: Session = Depends(get_db),
) -> list[ListingJobRead]:
    jobs = list_listing_jobs_service(db, status=status, limit=limit)
    serialize = serialize_listing_job_lite if lite else serialize_listing_job
    return [ListingJobRead(**serialize(db, job)) for job in jobs]


@router.get("/listing-jobs/automation-pause", response_model=ListingAutomationPauseStatus)
def read_listing_automation_pause(db: Session = Depends(get_db)) -> ListingAutomationPauseStatus:
    return ListingAutomationPauseStatus(**read_automation_pause(db))


@router.post("/listing-jobs/automation-pause", response_model=ListingAutomationPauseStatus)
def update_listing_automation_pause(
    payload: ListingAutomationPauseUpdate, db: Session = Depends(get_db)
) -> ListingAutomationPauseStatus:
    return ListingAutomationPauseStatus(**set_automation_pause(db, payload.paused, payload.reason))


@router.get("/listing-jobs/{job_id}", response_model=ListingJobRead)
def read_listing_job_route(job_id: int, db: Session = Depends(get_db)) -> ListingJobRead:
    """Serializing one job is cheap; the list endpoint rebuilds the eBay
    package and readiness for every job, which takes tens of seconds. The
    extension polls for a single tracked job, so it must not pay that cost."""
    job = read_listing_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Listing job not found")
    return ListingJobRead(**serialize_listing_job(db, job))


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


@router.post("/ebay/revision-jobs/canary", response_model=EbayRevisionJobRead)
def create_ebay_revision_canary_route(
    payload: EbayRevisionCanaryRequest,
    db: Session = Depends(get_db),
) -> EbayRevisionJobRead:
    try:
        job = create_ebay_revision_canary(
            db,
            product_id=payload.product_id,
            target_price=payload.target_price,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return EbayRevisionJobRead(**serialize_ebay_revision_job(db, job))


@router.post("/ebay/revision-sheets/prepare", response_model=EbayRevisionSheetPrepareResult)
def prepare_ebay_revision_sheet(
    payload: EbayRevisionSheetPrepareRequest,
    db: Session = Depends(get_db),
) -> EbayRevisionSheetPrepareResult:
    stored_template = read_ebay_revision_template(db, payload.account_key)
    template_csv = payload.template_csv or (stored_template.template_csv if stored_template is not None else "")
    if not template_csv:
        raise HTTPException(status_code=409, detail=f"No eBay price revision template is stored for {payload.account_key}")
    try:
        csv_content, job_ids = build_ebay_price_revision_csv(
            db,
            account_key=payload.account_key,
            job_ids=payload.job_ids,
            template_csv=template_csv,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    safe_account = "".join(character if character.isalnum() or character in "-_" else "-" for character in payload.account_key)
    return EbayRevisionSheetPrepareResult(
        account_key=payload.account_key,
        job_ids=job_ids,
        filename=f"autozs-price-revisions-{safe_account or 'account'}.csv",
        csv_content=csv_content,
    )


@router.put("/ebay/revision-templates/{account_key}", response_model=EbayRevisionTemplateRead)
def put_ebay_revision_template(
    account_key: str,
    payload: EbayRevisionTemplateUpdate,
    db: Session = Depends(get_db),
) -> EbayRevisionTemplateRead:
    try:
        template = save_ebay_revision_template(
            db,
            account_key=account_key,
            filename=payload.filename,
            template_csv=payload.template_csv,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return EbayRevisionTemplateRead.model_validate(template, from_attributes=True)


@router.get("/ebay/revision-templates/{account_key}", response_model=EbayRevisionTemplateRead)
def get_ebay_revision_template(account_key: str, db: Session = Depends(get_db)) -> EbayRevisionTemplateRead:
    template = read_ebay_revision_template(db, account_key)
    if template is None:
        raise HTTPException(status_code=404, detail="eBay revision template not found")
    return EbayRevisionTemplateRead.model_validate(template, from_attributes=True)


@router.post("/ebay/revision-batches/next", response_model=EbayRevisionBatchRead)
def next_ebay_revision_batch(
    account_key: str = Query(...),
    limit: int = Query(25, ge=1, le=150),
    db: Session = Depends(get_db),
) -> EbayRevisionBatchRead:
    try:
        batch = prepare_next_ebay_revision_batch(db, account_key=account_key, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if batch is None:
        raise HTTPException(status_code=404, detail="No approved eBay price revisions are queued")
    return EbayRevisionBatchRead(**serialize_ebay_revision_batch(batch, include_csv=True))


@router.get("/ebay/revision-batches", response_model=list[EbayRevisionBatchRead])
def read_ebay_revision_batches(
    account_key: str | None = None,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=250),
    db: Session = Depends(get_db),
) -> list[EbayRevisionBatchRead]:
    batches = list_ebay_revision_batches(
        db,
        account_key=account_key,
        status=status,
        limit=limit,
    )
    return [EbayRevisionBatchRead(**serialize_ebay_revision_batch(batch)) for batch in batches]


@router.get("/ebay/revision-batches/{batch_id}", response_model=EbayRevisionBatchRead)
def read_ebay_revision_batch(batch_id: int, db: Session = Depends(get_db)) -> EbayRevisionBatchRead:
    batch = db.get(EbayRevisionBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="eBay revision batch not found")
    return EbayRevisionBatchRead(**serialize_ebay_revision_batch(batch, include_csv=True))


@router.patch("/ebay/revision-batches/{batch_id}", response_model=EbayRevisionBatchRead)
def patch_ebay_revision_batch(
    batch_id: int,
    payload: EbayRevisionBatchUpdate,
    db: Session = Depends(get_db),
) -> EbayRevisionBatchRead:
    batch = db.get(EbayRevisionBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="eBay revision batch not found")
    try:
        batch = update_ebay_revision_batch(db, batch, status=payload.status, message=payload.message)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return EbayRevisionBatchRead(**serialize_ebay_revision_batch(batch))


@router.post("/ebay/revision-batches/{batch_id}/results", response_model=EbayRevisionBatchRead)
def import_ebay_revision_batch_results(
    batch_id: int,
    payload: EbayRevisionBatchResultImport,
    db: Session = Depends(get_db),
) -> EbayRevisionBatchRead:
    batch = db.get(EbayRevisionBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="eBay revision batch not found")
    try:
        result_csv = decode_ebay_revision_result(
            filename=payload.filename,
            result_csv=payload.result_csv,
            result_base64=payload.result_base64,
        )
        batch = import_ebay_revision_result(db, batch, result_csv=result_csv, filename=payload.filename)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return EbayRevisionBatchRead(**serialize_ebay_revision_batch(batch))


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
    configured_accounts = list(db.scalars(select(EbayAccount)).all())
    account_aliases = {
        alias: configured.key
        for configured in configured_accounts
        for alias in (configured.key, configured.account_id)
        if alias
    }
    raw_account_ids = {
        *{order.account_id for order in orders if getattr(order, "account_id", None)},
        *{listing.account_id for listing in listings if getattr(listing, "account_id", None)},
        *{configured.key for configured in configured_accounts if configured.key},
        *{configured.account_id for configured in configured_accounts if configured.account_id},
    }
    available_accounts = sorted({account_aliases.get(raw, raw) for raw in raw_account_ids})
    selected_account = account_aliases.get(account, account)
    selected_aliases = {
        alias
        for alias, canonical in account_aliases.items()
        if canonical == selected_account
    } | {selected_account}
    if selected_account != "all":
        account_orders = [
            order
            for order in orders
            if order.account_id in selected_aliases and _in_stats_range(order.created_at, cutoff)
        ]
        account_listings = [
            listing
            for listing in listings
            if listing.account_id in selected_aliases and _in_stats_range(listing.created_at, cutoff)
        ]
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
        minimum_order_quantity = max(1, int(supplier.minimum_order_quantity or 1)) if supplier else 1
        draft_price = draft.calculated_price if draft else None
        cost = round(effective_supplier_cost(source_price * minimum_order_quantity, settings) + _shipping_cost(source_shipping), 2) if source_price is not None else 0.0
        fees = _stats_fees(product, draft_price)
        profit = _stats_profit(product, draft_price, source_price, source_shipping, settings, minimum_order_quantity)
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
        selected_account=selected_account,
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


@router.get("/stats/traffic", response_model=EbayTrafficOverviewRead)
def read_traffic_overview(
    selected_range: str = Query("30", alias="range", pattern="^(7|30|90|all)$"),
    grain: str = Query("day", pattern="^(day|month)$"),
    account: str = Query("all", pattern="^[A-Za-z0-9_.:-]+$"),
    db: Session = Depends(get_db),
) -> EbayTrafficOverviewRead:
    return EbayTrafficOverviewRead(
        **traffic_overview(
            db,
            selected_range=selected_range,
            grain=grain,
            account=account,
        )
    )


@router.post("/stats/traffic/sync", response_model=EbayTrafficSyncResult)
def refresh_traffic_metrics(
    selected_range: str = Query("30", alias="range", pattern="^(7|30|90|all)$"),
    account: str = Query("all", pattern="^[A-Za-z0-9_.:-]+$"),
    db: Session = Depends(get_db),
) -> EbayTrafficSyncResult:
    try:
        return EbayTrafficSyncResult(
            **sync_ebay_traffic(
                db,
                selected_range=selected_range,
                account=account,
            )
        )
    except ValueError:
        account_key = account
        if account_key == "all":
            configured = list_ebay_accounts(db)
            if not configured:
                raise HTTPException(status_code=409, detail="No eBay store is configured for Chrome traffic sync.")
            account_key = str(configured[0]["key"])
        run = queue_ebay_traffic_sync(db, account_key=account_key, force=True)
        today = datetime.utcnow().date()
        return EbayTrafficSyncResult(
            records_imported=0,
            accounts_synced=[],
            period_start=(today - timedelta(days=29)).isoformat(),
            period_end=today.isoformat(),
            queued=run.status in {"queued", "running"},
            run_id=run.id,
        )


@router.post("/stats/traffic/import", response_model=EbayTrafficImportResult)
def import_traffic_metrics(
    payload: EbayTrafficReportImport,
    db: Session = Depends(get_db),
) -> EbayTrafficImportResult:
    imported = import_traffic_report(
        db,
        account_key=payload.account_key,
        account_id=payload.account_id or payload.account_key,
        marketplace_id=payload.marketplace_id,
        payload=payload.report,
        dimension=payload.dimension,
    )
    db.commit()
    return EbayTrafficImportResult(records_imported=imported)


@router.post("/stats/traffic/import-file", response_model=EbayTrafficImportResult)
def import_traffic_metrics_file(
    payload: EbayTrafficFileImport,
    db: Session = Depends(get_db),
) -> EbayTrafficImportResult:
    try:
        imported = import_traffic_file(
            db,
            account_key=payload.account_key,
            filename=payload.filename,
            report_base64=payload.report_base64,
            run_id=payload.run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EbayTrafficImportResult(records_imported=imported)


@router.get("/repricing/snapshots", response_model=list[PriceSnapshotRead])
def list_repricing_snapshots(db: Session = Depends(get_db)) -> list[PriceSnapshot]:
    return list(db.scalars(select(PriceSnapshot).order_by(PriceSnapshot.created_at.desc()).limit(100)).all())


@router.post("/orders/sync-sandbox", response_model=OrderRead)
def sync_sandbox_order(db: Session = Depends(get_db)) -> Order:
    return seed_mock_order(db)


@router.post("/orders/sync", response_model=EbaySyncRunRead)
def queue_order_sync(
    account_key: str = Query(DEFAULT_EBAY_STORE_KEY, min_length=1, max_length=128),
    db: Session = Depends(get_db),
) -> EbaySyncRunRead:
    run = queue_ebay_order_sync(db, account_key=account_key, force=True)
    return EbaySyncRunRead(**serialize_ebay_sync_run(run))


@router.post("/orders/sync/next", response_model=EbaySyncRunRead | None)
def claim_order_sync(
    account_key: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db),
) -> EbaySyncRunRead | None:
    run = claim_next_ebay_order_sync(db, account_key=account_key)
    return EbaySyncRunRead(**serialize_ebay_sync_run(run)) if run else None


@router.post("/orders/import-file", response_model=EbayOrderReportImportResult)
def import_order_report(
    payload: EbayOrderReportImport,
    db: Session = Depends(get_db),
) -> EbayOrderReportImportResult:
    try:
        content = base64.b64decode(payload.report_base64, validate=True)
        rows = parse_ebay_order_report(content, payload.filename)
        seen, upserted, unmatched = import_ebay_order_report_rows(
            db,
            rows=rows,
            account_key=payload.account_key,
            run_id=payload.run_id,
            filename=payload.filename,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EbayOrderReportImportResult(
        orders_seen=seen,
        orders_upserted=upserted,
        unmatched_items=unmatched,
        run_id=payload.run_id,
    )


@router.get("/orders", response_model=list[OrderRead])
def list_orders(include_sandbox: bool = False, db: Session = Depends(get_db)) -> list[Order]:
    stmt = (
        select(Order)
        .options(
            selectinload(Order.items),
            selectinload(Order.fulfillment_tasks),
            selectinload(Order.customer_updates),
            selectinload(Order.supplier_orders).selectinload(SupplierOrder.items),
        )
        .order_by(Order.created_at.desc())
    )
    if not include_sandbox:
        stmt = stmt.where(Order.ebay_order_id != "SANDBOX-ORDER-001")
    return list(db.scalars(stmt).all())


@router.get("/gift-cards", response_model=list[GiftCardRead])
def read_gift_cards(db: Session = Depends(get_db)) -> list[GiftCard]:
    return list_gift_cards(db)


@router.post("/gift-cards", response_model=GiftCardRead)
def add_gift_card(payload: GiftCardCreate, db: Session = Depends(get_db)) -> GiftCard:
    try:
        return create_gift_card(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/gift-cards/{card_id}", response_model=GiftCardRead)
def patch_gift_card(card_id: int, payload: GiftCardUpdate, db: Session = Depends(get_db)) -> GiftCard:
    card = db.get(GiftCard, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Gift card not found")
    try:
        return update_gift_card(db, card, **payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/gift-cards/{card_id}/credential", response_model=GiftCardCredentialStatus)
def store_gift_card_credential(
    card_id: int,
    payload: GiftCardCredentialWrite,
    request: Request,
    db: Session = Depends(get_db),
) -> GiftCardCredentialStatus:
    _require_local_checkout_request(request)
    card = db.get(GiftCard, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Gift card not found")
    target = gift_card_credential_target(card.id)
    try:
        store_generic_credential(target, payload.card_number, payload.pin)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    card.secret_ref = target
    card.last_four = "".join(character for character in payload.card_number if character.isdigit())[-4:]
    db.commit()
    return GiftCardCredentialStatus(stored=True, secret_ref=target, last_four=card.last_four)


@router.get("/supplier-orders", response_model=list[SupplierOrderRead])
def read_supplier_orders(order_id: int | None = None, db: Session = Depends(get_db)) -> list[SupplierOrder]:
    return list_supplier_orders(db, order_id=order_id)


@router.get("/supplier-orders/{supplier_order_id}", response_model=SupplierOrderRead)
def read_supplier_order(supplier_order_id: int, db: Session = Depends(get_db)) -> SupplierOrder:
    orders = list_supplier_orders(db)
    supplier_order = next((order for order in orders if order.id == supplier_order_id), None)
    if supplier_order is None:
        raise HTTPException(status_code=404, detail="Supplier order not found")
    return supplier_order


@router.post("/orders/{order_id}/supplier-orders/prepare", response_model=SupplierOrderRead)
def prepare_order_for_supplier(
    order_id: int,
    payload: SupplierOrderPrepare,
    db: Session = Depends(get_db),
) -> SupplierOrder:
    try:
        return prepare_supplier_order(db, order_id, **payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/supplier-orders/{supplier_order_id}/approve", response_model=SupplierOrderRead)
def approve_order_for_supplier(supplier_order_id: int, db: Session = Depends(get_db)) -> SupplierOrder:
    try:
        return approve_supplier_order(db, supplier_order_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/supplier-orders/next", response_model=SupplierOrderClaimRead | None)
def claim_supplier_order(db: Session = Depends(get_db)) -> SupplierOrder | None:
    return claim_next_supplier_order(db)


@router.post(
    "/supplier-orders/{supplier_order_id}/checkout-credential",
    response_model=SupplierCheckoutCredentialRead,
)
def read_supplier_checkout_credential(
    supplier_order_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SupplierCheckoutCredentialRead:
    _require_local_checkout_request(request)
    supplier_order = db.get(SupplierOrder, supplier_order_id)
    if supplier_order is None:
        raise HTTPException(status_code=404, detail="Supplier order not found")
    token = request.headers.get("X-AutoZS-Checkout-Token", "")
    if (
        supplier_order.status != "placing"
        or not supplier_order.checkout_token
        or not hmac.compare_digest(token, supplier_order.checkout_token)
    ):
        raise HTTPException(status_code=403, detail="The checkout credential lease is not valid.")
    card = db.get(GiftCard, supplier_order.gift_card_id) if supplier_order.gift_card_id else None
    if card is None or card.status != "active" or not card.secret_ref:
        raise HTTPException(status_code=422, detail="An active secured gift card is required.")
    if float(card.current_balance or 0) + 0.001 < float(supplier_order.approved_total or 0):
        raise HTTPException(status_code=422, detail="Gift-card balance is below the approved supplier-order total.")
    try:
        card_number, pin = read_generic_credential(card.secret_ref)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return SupplierCheckoutCredentialRead(
        supplier_order_id=supplier_order.id,
        card_number=card_number,
        pin=pin,
        approved_total=float(supplier_order.approved_total or 0),
        current_balance=float(card.current_balance or 0),
    )


@router.patch("/supplier-orders/{supplier_order_id}", response_model=SupplierOrderRead)
def patch_supplier_order(
    supplier_order_id: int,
    payload: SupplierOrderUpdate,
    db: Session = Depends(get_db),
) -> SupplierOrder:
    supplier_order = db.get(SupplierOrder, supplier_order_id)
    if supplier_order is None:
        raise HTTPException(status_code=404, detail="Supplier order not found")
    try:
        return update_supplier_order(db, supplier_order, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/orders/{order_id}/customer-updates", response_model=OrderUpdateDraftRunRead)
def draft_order_customer_update(order_id: int, db: Session = Depends(get_db)) -> OrderUpdateDraftRunRead:
    if db.get(Order, order_id) is None:
        raise HTTPException(status_code=404, detail="Order not found")
    updates = generate_order_update_drafts(db, order_id=order_id)
    return OrderUpdateDraftRunRead(drafted=len(updates), updates=updates)


@router.get("/customer-updates", response_model=list[CustomerUpdateRead])
def read_customer_updates(status: str | None = Query(None, pattern="^(draft|sent|skipped)$"), db: Session = Depends(get_db)) -> list[CustomerUpdate]:
    return list_customer_updates(db, status=status)


@router.get("/customer-service/conversations", response_model=list[CustomerConversationRead])
def read_customer_conversations(db: Session = Depends(get_db)) -> list[CustomerConversation]:
    return list_conversations(db)


@router.get("/customer-service/templates", response_model=list[CustomerTemplateRead])
def read_customer_templates() -> list[dict]:
    return list_customer_templates()


@router.post("/customer-service/automation/post-sale")
def queue_post_sale_customer_messages(db: Session = Depends(get_db)) -> dict[str, int]:
    queued = queue_missing_order_thank_yous(db)
    return {"queued": len(queued)}


@router.post("/customer-service/templates/{template_key}/render", response_model=CustomerTemplateRenderRead)
def preview_customer_template(
    template_key: str,
    payload: CustomerTemplateRenderRequest,
) -> dict:
    try:
        return render_customer_template(template_key, payload.variables)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/customer-service/conversations/import", response_model=CustomerConversationRead)
def import_customer_conversation(
    payload: CustomerConversationImport,
    db: Session = Depends(get_db),
) -> CustomerConversation:
    return import_conversation(
        db,
        account_id=payload.account_id,
        ebay_thread_id=payload.ebay_thread_id,
        ebay_order_id=payload.ebay_order_id,
        buyer_username=payload.buyer_username,
        subject=payload.subject,
        messages=[message.model_dump() for message in payload.messages],
    )


@router.post("/customer-service/conversations/{conversation_id}/messages", response_model=CustomerMessageRead)
def create_customer_message(
    conversation_id: int,
    payload: CustomerMessageCreate,
    db: Session = Depends(get_db),
) -> CustomerMessage:
    try:
        return queue_message(db, conversation_id, **payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/customer-service/conversations/{conversation_id}/template-messages",
    response_model=CustomerMessageRead,
)
def create_customer_template_message(
    conversation_id: int,
    template_key: str,
    payload: CustomerTemplateMessageCreate,
    db: Session = Depends(get_db),
) -> CustomerMessage:
    try:
        return queue_template_message(
            db,
            conversation_id,
            template_key=template_key,
            **payload.model_dump(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/customer-service/messages/next", response_model=CustomerMessageRead | None)
def claim_customer_message(db: Session = Depends(get_db)) -> CustomerMessage | None:
    return claim_next_outbound_message(db)


@router.patch("/customer-service/messages/{message_id}", response_model=CustomerMessageRead)
def patch_customer_message(
    message_id: int,
    payload: CustomerMessageUpdate,
    db: Session = Depends(get_db),
) -> CustomerMessage:
    message = db.get(CustomerMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Customer message not found")
    return update_message(db, message, payload.model_dump(exclude_unset=True))


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


@router.get("/finance/overview", response_model=FinanceOverviewRead)
def read_finance_overview(db: Session = Depends(get_db)) -> FinanceOverviewRead:
    return FinanceOverviewRead(**finance_overview(db))


@router.post("/finance/accounts", response_model=FinancialAccountRead)
def write_financial_account(
    payload: FinancialAccountUpsert,
    db: Session = Depends(get_db),
) -> FinancialAccount:
    return upsert_financial_account(db, payload.model_dump())


@router.post("/finance/subscriptions", response_model=SubscriptionExpenseRead)
def add_subscription_expense(
    payload: SubscriptionExpenseCreate,
    db: Session = Depends(get_db),
) -> SubscriptionExpense:
    if payload.payment_account_id is not None and db.get(FinancialAccount, payload.payment_account_id) is None:
        raise HTTPException(status_code=422, detail="Payment account not found")
    return create_subscription(db, payload.model_dump())


@router.post("/finance/entries/import")
def import_financial_entries(entries: list[FinanceEntryImport], db: Session = Depends(get_db)) -> dict[str, int]:
    return {"imported": import_finance_entries(db, [entry.model_dump() for entry in entries])}


@router.get("/api/z-finance/summary", dependencies=[Depends(_require_z_finance_bearer)])
def read_z_finance_summary(
    period: str = Query("all"),
    start_date: date | None = Query(None, alias="startDate"),
    end_date: date | None = Query(None, alias="endDate"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return build_z_finance_summary(
            db,
            period,
            start_date,
            end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/z-finance/orders", dependencies=[Depends(_require_z_finance_bearer)])
def read_z_finance_orders(
    period: str = Query("all"),
    start_date: date | None = Query(None, alias="startDate"),
    end_date: date | None = Query(None, alias="endDate"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return build_z_finance_orders(
            db,
            period,
            start_date,
            end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/z-finance/payouts", dependencies=[Depends(_require_z_finance_bearer)])
def read_z_finance_payouts(
    period: str = Query("all"),
    start_date: date | None = Query(None, alias="startDate"),
    end_date: date | None = Query(None, alias="endDate"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return build_z_finance_payouts(
            db,
            period,
            start_date,
            end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/z-finance/sync", dependencies=[Depends(_require_z_finance_bearer)])
def run_z_finance_sync(payload: ZFinanceSyncRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return sync_from_z_finance(
            db,
            start_date=payload.startDate,
            end_date=payload.endDate,
            reset_cursor=payload.resetCursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Z Finance sync failed") from exc


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
    minimum_order_quantity: int = 1,
) -> float | None:
    if draft_price is None or source_price is None:
        return None
    fee_rate = product.ebay_fee_rate + product.promoted_rate + product.return_risk_rate
    return round(
        draft_price
        - effective_supplier_cost(source_price * max(1, minimum_order_quantity), settings)
        - _shipping_cost(source_shipping)
        - (draft_price * fee_rate),
        2,
    )


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

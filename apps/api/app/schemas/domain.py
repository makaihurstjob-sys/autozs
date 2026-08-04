from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResearchJobCreate(BaseModel):
    source: str = Field(pattern="^(competitor|keyword)$")
    query: str = Field(min_length=2, max_length=512)


class ResearchJobRead(BaseModel):
    id: int
    source: str
    query: str
    status: str
    message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CandidateRead(BaseModel):
    id: int
    source: str
    external_id: str
    title: str
    listing_url: str | None = None
    image_url: str | None = None
    competitor_price: float | None = None
    estimated_sold: int | None = None
    seller_username: str | None = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompetitorUpsert(BaseModel):
    username: str = Field(min_length=2, max_length=128)
    seed_listing_url: str | None = None
    notes: str | None = None


class CompetitorRead(BaseModel):
    id: int
    username: str | None = None
    seed_listing_url: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupplierAttach(BaseModel):
    supplier: str = "home_depot"
    source_url: str
    supplier_sku: str | None = None
    last_price: float | None = None
    last_shipping: float = -1.0
    subscription_discount_percent: float | None = Field(default=None, ge=0, le=100)
    minimum_order_quantity: int = Field(default=1, ge=1, le=999)
    in_stock: bool = True
    price_unavailable: bool = False


class SupplierRead(BaseModel):
    id: int
    supplier: str
    source_url: str
    supplier_sku: str | None = None
    last_price: float | None = None
    last_shipping: float
    subscription_discount_percent: float | None = None
    minimum_order_quantity: int = 1
    in_stock: bool
    price_unavailable: bool = False
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupplierOptionRead(BaseModel):
    key: str
    label: str
    enabled: bool
    status: str
    domains: list[str] = []
    capabilities: dict[str, bool] = {}
    note: str


class ProductImageRead(BaseModel):
    id: int
    image_url: str
    local_path: str | None = None
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ProductImageOrderUpdate(BaseModel):
    image_ids: list[int] = Field(min_length=1)


class ListingDraftRead(BaseModel):
    id: int
    marketplace: str
    title: str
    description: str
    source_price: float | None = None
    calculated_price: float | None = None
    margin_percent: float
    ebay_fee_rate: float
    status: str

    model_config = ConfigDict(from_attributes=True)


class ProductRead(BaseModel):
    id: int
    sku: str
    title: str
    status: str
    competitor_listing_url: str | None = None
    competitor_price: float | None = None
    desired_profit: float
    risk_buffer: float
    undercut_amount: float
    listing_schedule_at: datetime | None = None
    supplier_products: list[SupplierRead] = []
    images: list[ProductImageRead] = []
    listing_drafts: list[ListingDraftRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductImportRequest(BaseModel):
    urls: str
    supplier_override: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,31}$")
    source_price_override: float | None = None
    source_shipping_override: float | None = None
    competitor_price: float | None = None


class ProductListingScheduleUpdate(BaseModel):
    listing_schedule_at: datetime | None = None


class SourceCaptureQueueItem(BaseModel):
    product_id: int
    sku: str
    title: str
    source_url: str
    missing: list[str]
    reason: str
    source_price: float | None = None
    source_shipping: float | None = None
    image_count: int
    local_image_count: int
    item_specifics: dict[str, str] = Field(default_factory=dict)
    updated_at: datetime


class SourceCaptureQueueRead(BaseModel):
    total: int
    items: list[SourceCaptureQueueItem]


class SourceCaptureClaim(BaseModel):
    worker_id: str = Field(min_length=1, max_length=256)
    source_host: str | None = Field(default=None, max_length=128)


class CapturedProductUpdate(BaseModel):
    title: str | None = None
    source_price: float | None = Field(default=None, ge=0)
    source_shipping: float | None = Field(default=None, ge=0)
    source_in_stock: bool | None = None
    source_price_unavailable: bool | None = None
    competitor_price: float | None = Field(default=None, ge=0)
    subscription_discount_percent: float | None = Field(default=None, ge=0, le=100)
    minimum_order_quantity: int | None = Field(default=None, ge=1, le=999)
    source_purchase_unit: str | None = Field(default=None, max_length=32)
    source_bulk_package: bool = False
    source_bulk_package_reason: str | None = Field(default=None, max_length=512)
    description: str | None = None
    image_urls: str | None = None


class CapturedProductImport(BaseModel):
    source_url: str
    title: str
    source_price: float | None = Field(default=None, ge=0)
    source_shipping: float | None = Field(default=None, ge=0)
    source_in_stock: bool | None = None
    source_price_unavailable: bool | None = None
    competitor_price: float | None = Field(default=None, ge=0)
    subscription_discount_percent: float | None = Field(default=None, ge=0, le=100)
    minimum_order_quantity: int | None = Field(default=None, ge=1, le=999)
    source_purchase_unit: str | None = Field(default=None, max_length=32)
    source_bulk_package: bool = False
    source_bulk_package_reason: str | None = Field(default=None, max_length=512)
    description: str | None = None
    image_urls: str | None = None
    refresh_job_id: int | None = Field(default=None, ge=1)


class DraftPriceUpdate(BaseModel):
    mode: str = Field(pattern="^(margin|competitor|safe_competitor|minimum_profit)$")


class ProductImportResult(BaseModel):
    imported: int
    products: list[ProductRead]
    warnings: list[str] = []


class DraftRecalculationResult(BaseModel):
    updated: int
    products: list[ProductRead]
    revision_jobs_queued: int = 0
    revision_jobs_updated: int = 0


class ProductImageDownloadResult(BaseModel):
    product_id: int
    attempted: int
    downloaded: int
    images: list[ProductImageRead]


class ProductImagePrepResult(BaseModel):
    product_id: int
    attempted: int
    prepared: int
    size: int
    images: list[ProductImageRead]


class BulkProductImageDownloadResult(BaseModel):
    products_checked: int
    products_attempted: int
    attempted: int
    downloaded: int
    results: list[ProductImageDownloadResult]


class EbayListingPackage(BaseModel):
    product_id: int
    sku: str
    title: str
    price: float | None = None
    quantity: int = 1
    condition: str = "New"
    description: str
    item_specifics: dict[str, str] = Field(default_factory=dict)
    image_urls: list[str]
    local_image_paths: list[str]
    manual_image_paths: list[str]
    image_upload_status: str
    source_url: str | None = None
    source_price: float | None = None
    minimum_order_quantity: int = 1
    source_order_subtotal: float | None = None
    source_shipping: float = 0.0
    landed_cost: float | None = None
    effective_source_cost: float | None = None
    gift_card_discount_enabled: bool = False
    gift_card_discount_percent: float = 0.0
    sales_tax_percent: float = 0.0
    sales_tax_cost: float | None = None
    competitor_price: float | None = None
    margin_price: float | None = None
    competitor_target_price: float | None = None
    minimum_profit_price: float | None = None
    safe_competitor_price: float | None = None
    fee_rate_total: float
    estimated_fees: float | None = None
    estimated_profit: float | None = None
    minimum_profit: float
    profit_gap: float | None = None
    meets_minimum_profit: bool | None = None
    margin_price_profit: float | None = None
    competitor_target_profit: float | None = None
    minimum_profit_price_profit: float | None = None
    safe_competitor_price_profit: float | None = None
    warnings: list[str] = []
    pricing_strategy: str
    price_reason: str
    offers_enabled: bool = False
    listing_schedule_mode: str = "now"
    listing_schedule_at: str | None = None
    shipping_cost_type: str = "flat"
    domestic_shipping_service: str = "Economy Shipping"
    buyer_shipping_cost: float = 0.0
    manual_posting_steps: list[str]


class EbayExportResult(BaseModel):
    product_id: int
    export_dir: str
    listing_json_path: str
    description_html_path: str
    image_manifest_path: str
    macro_script_path: str
    api_payload_path: str
    zip_path: str
    files: list[str]


class EbayApiPayload(BaseModel):
    product_id: int
    sku: str
    environment: str = "sandbox"
    inventory_item_endpoint: str
    offer_endpoint: str
    publish_endpoint_template: str
    inventory_item_payload: dict
    offer_payload: dict
    publish_payload: dict
    missing_publish_requirements: list[str]


class EbayManualMacro(BaseModel):
    product_id: int
    sku: str
    title: str
    price: float | None = None
    manual_ready: bool
    missing_manual: list[str]
    warnings: list[str]
    script: str


class EbayPublishResult(BaseModel):
    product_id: int
    sku: str
    environment: str
    inventory_item_status_code: int
    offer_status_code: int
    publish_status_code: int
    offer_id: str
    listing_id: str
    listing_status: str
    warnings: list[str] = []


class EbayListingRead(BaseModel):
    id: int
    product_id: int
    listing_id: str
    account_id: str
    environment: str
    price: float | None = None
    quantity: int
    status: str
    started_at: datetime | None = None
    renews_at: datetime | None = None
    views: int = 0
    view_delta: int | None = None
    views_measured_at: datetime | None = None
    days_until_relist: int | None = None
    auto_delist_candidate: bool = False
    removal_reason: str | None = None
    removal_detail: str | None = None
    removed_at: datetime | None = None
    relist_blocked: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EbayListingTombstoneRequest(BaseModel):
    """Record why a listing stopped being active.

    ``reason`` is a short machine-ish tag (``takedown``, ``duplicate``, ``ended``).
    ``block_relist`` should be true for eBay takedowns so nothing re-publishes the
    item until a human clears it.
    """

    reason: str = "ended"
    detail: str = ""
    block_relist: bool = False


class EbayListingViewSnapshotRead(BaseModel):
    id: int
    ebay_listing_id: int
    sync_run_id: int | None = None
    views: int
    captured_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EbayListingViewsSummary(BaseModel):
    account_key: str | None = None
    views_30d: int = 0
    views_7d: int = 0
    listings_measured: int = 0
    measured_at: datetime | None = None


class EbayTrafficReportImport(BaseModel):
    account_key: str = Field(default="manual", min_length=1, max_length=128)
    account_id: str = Field(default="", max_length=128)
    marketplace_id: str = Field(default="EBAY_US", max_length=32)
    dimension: str | None = Field(default=None, pattern="^(DAY|LISTING)$")
    report: dict


class EbayTrafficSyncResult(BaseModel):
    records_imported: int
    accounts_synced: list[str]
    period_start: str
    period_end: str
    queued: bool = False
    run_id: int | None = None


class EbayTrafficImportResult(BaseModel):
    records_imported: int


class EbayTrafficFileImport(BaseModel):
    account_key: str = Field(default="manual", min_length=1, max_length=128)
    run_id: int | None = None
    filename: str = Field(default="ebay-active-listings-traffic.csv", max_length=512)
    report_base64: str = Field(min_length=1)


class EbayTrafficMetricRead(BaseModel):
    key: str
    label: str
    value: float | None = None


class EbayTrafficSourceRead(BaseModel):
    key: str
    label: str
    views: float = 0.0
    impressions: float = 0.0


class EbayTrafficTrendPoint(BaseModel):
    label: str
    total_impressions: float = 0.0
    listing_impressions: float = 0.0
    search_impressions: float = 0.0
    store_impressions: float = 0.0
    total_views: float = 0.0
    direct_views: float = 0.0
    off_ebay_views: float = 0.0
    other_ebay_views: float = 0.0
    search_views: float = 0.0
    store_views: float = 0.0
    transactions: float = 0.0
    promoted_impressions: float = 0.0
    promoted_views: float = 0.0
    promoted_transactions: float = 0.0
    sales_amount: float = 0.0
    click_through_rate: float = 0.0
    sales_conversion_rate: float = 0.0


class EbayTrafficListingInsight(BaseModel):
    listing_id: str
    title: str
    sku: str | None = None
    total_impressions: float = 0.0
    total_views: float = 0.0
    click_through_rate: float = 0.0
    transactions: float = 0.0
    sales_conversion_rate: float = 0.0
    sales_amount: float | None = None
    opportunity_score: float = 0.0


class EbayTrafficOverviewRead(BaseModel):
    selected_range: str
    grain: str
    selected_account: str
    data_source: str
    last_updated_at: datetime | None = None
    stale: bool = True
    summary: dict[str, float | int | None]
    trend: list[EbayTrafficTrendPoint]
    best_listings: list[EbayTrafficListingInsight]
    worst_listings: list[EbayTrafficListingInsight]
    opportunities: list[EbayTrafficListingInsight]
    source_breakdown: list[EbayTrafficSourceRead]
    available_metrics: list[EbayTrafficMetricRead]


class EbayListingMarkRequest(BaseModel):
    listing_id: str | None = None
    account_id: str = "manual"
    environment: str = "manual"
    quantity: int = Field(default=1, ge=0)
    status: str = "listed"


class EbaySyncRunCreate(BaseModel):
    account_key: str = Field(default="manual", min_length=1, max_length=128)
    source: str = Field(default="seller_hub_report", max_length=64)
    report_type: str = Field(default="active_listings", pattern="^(active_listings|traffic|orders)$")


class EbaySyncRunProgress(BaseModel):
    phase: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=32)
    message: str | None = Field(default=None, max_length=2000)
    report_reference: str | None = Field(default=None, max_length=128)
    report_filename: str | None = Field(default=None, max_length=1000)
    increment_attempts: bool = False
    listings_seen: int | None = Field(default=None, ge=0)
    listings_upserted: int | None = Field(default=None, ge=0)
    orders_seen: int | None = Field(default=None, ge=0)
    orders_upserted: int | None = Field(default=None, ge=0)


class EbaySyncListingReportRow(BaseModel):
    listing_id: str | None = Field(default=None, max_length=128)
    item_id: str | None = Field(default=None, max_length=128)
    item_number: str | None = Field(default=None, max_length=128)
    ebay_item_id: str | None = Field(default=None, max_length=128)
    draft_id: str | None = Field(default=None, max_length=128)
    ebay_draft_id: str | None = Field(default=None, max_length=128)
    sku: str | None = Field(default=None, max_length=64)
    custom_label: str | None = Field(default=None, max_length=64)
    seller_sku: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=512)
    item_title: str | None = Field(default=None, max_length=512)
    listing_title: str | None = Field(default=None, max_length=512)
    status: str | None = Field(default=None, max_length=64)
    listing_status: str | None = Field(default=None, max_length=64)
    state: str | None = Field(default=None, max_length=64)
    price: str | float | int | None = None
    current_price: str | float | int | None = None
    start_price: str | float | int | None = None
    buy_it_now_price: str | float | int | None = None
    quantity: str | int | None = None
    available_quantity: str | int | None = None
    qty: str | int | None = None
    views: str | int | None = None
    view_count: str | int | None = None
    page_views: str | int | None = None
    listing_views: str | int | None = None
    live_on: str | datetime | None = None
    started_at: str | datetime | None = None
    start_date: str | datetime | None = None
    listing_start_date: str | datetime | None = None
    renews_on: str | datetime | None = None
    renews_at: str | datetime | None = None
    renewal_date: str | datetime | None = None
    relist_date: str | datetime | None = None
    end_date: str | datetime | None = None
    ends_on: str | datetime | None = None
    environment: str | None = Field(default=None, max_length=32)


class EbaySyncListingReportImport(BaseModel):
    account_key: str = Field(default="manual", min_length=1, max_length=128)
    run_id: int | None = None
    source: str = Field(default="manual_report", max_length=64)
    tombstone_missing: bool = True
    rows: list[EbaySyncListingReportRow] = Field(min_length=1)


class EbayListingViewsCapture(BaseModel):
    account_key: str = Field(default="manual", min_length=1, max_length=128)
    run_id: int | None = None
    rows: list[EbaySyncListingReportRow] = Field(min_length=1)


class EbayListingViewsCaptureResult(BaseModel):
    captured: int
    unmatched: int


class EbaySyncRunRead(BaseModel):
    id: int
    account_key: str
    status: str
    phase: str
    source: str
    report_type: str
    report_reference: str | None = None
    report_filename: str | None = None
    attempts: int = 0
    runner_url: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    listings_seen: int
    listings_upserted: int
    listings_imported: int
    listings_tombstoned: int
    orders_seen: int
    orders_upserted: int
    revision_jobs_queued: int
    message: str | None = None
    created_at: datetime
    updated_at: datetime


class EbayRevisionEnqueueRequest(BaseModel):
    product_ids: list[int] | None = None


class EbayRevisionCanaryRequest(BaseModel):
    product_id: int
    target_price: float = Field(gt=0)
    reason: str = Field(default="Controlled price-revision canary", max_length=240)


class EbayRevisionEnqueueResult(BaseModel):
    queued: int
    updated: int


class EbayRevisionSheetPrepareRequest(BaseModel):
    account_key: str
    job_ids: list[int]
    template_csv: str | None = None


class EbayRevisionSheetPrepareResult(BaseModel):
    account_key: str
    job_ids: list[int]
    filename: str
    csv_content: str


class EbayRevisionTemplateUpdate(BaseModel):
    filename: str
    template_csv: str


class EbayRevisionTemplateRead(BaseModel):
    account_key: str
    filename: str
    created_at: datetime
    updated_at: datetime


class EbayRevisionBatchUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(prepared|uploading|waiting_results|completed|needs_review|failed|cancelled)$")
    message: str | None = None


class EbayRevisionBatchResultImport(BaseModel):
    filename: str = ""
    result_csv: str = ""
    result_base64: str | None = None


class EbayRevisionBatchRead(BaseModel):
    id: int
    account_key: str
    status: str
    job_ids: list[int]
    filename: str
    result_filename: str | None = None
    rows_total: int
    rows_succeeded: int
    rows_failed: int
    attempts: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    message: str | None = None
    runner_url: str
    csv_content: str | None = None
    created_at: datetime
    updated_at: datetime


class EbayRevisionJobUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(needs_review|queued|running|completed|failed|paused|cancelled)$")
    message: str | None = None


class EbayRevisionJobRead(BaseModel):
    id: int
    product_id: int
    ebay_listing_id: int
    listing_id: str
    title: str
    ebay_account_key: str
    action: str
    status: str
    old_price: float | None = None
    target_price: float
    old_source_price: float | None = None
    source_price: float | None = None
    minimum_order_quantity: int = 1
    source_order_subtotal: float | None = None
    source_shipping: float = 0.0
    source_url: str | None = None
    projected_profit: float | None = None
    minimum_profit: float | None = None
    guard_passed: bool = False
    guard_reason: str | None = None
    approval_required: bool = True
    approved_at: datetime | None = None
    lease_expires_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempts: int
    message: str | None = None
    assistant_url: str
    created_at: datetime
    updated_at: datetime


class ListingReadinessReport(BaseModel):
    product_id: int
    sku: str
    manual_ready: bool
    api_ready: bool
    missing_manual: list[str]
    missing_api: list[str]
    warnings: list[str]
    checks: dict[str, bool]


class ListingQueueItem(BaseModel):
    product_id: int
    sku: str
    title: str
    price: float | None = None
    estimated_profit: float | None = None
    meets_minimum_profit: bool | None = None
    image_upload_status: str
    image_count: int
    local_image_count: int
    manual_ready: bool
    api_ready: bool
    missing_manual: list[str]
    missing_api: list[str]
    warnings: list[str]
    item_specifics: dict[str, str] = Field(default_factory=dict)
    source_url: str | None = None
    listing_id: str | None = None
    listing_status: str | None = None
    listing_account_id: str | None = None
    listing_started_at: datetime | None = None
    listing_renews_at: datetime | None = None
    listing_views: int = 0
    listing_view_delta: int | None = None
    listing_views_measured_at: datetime | None = None
    days_until_relist: int | None = None
    auto_delist_candidate: bool = False


class ListingJobCreate(BaseModel):
    product_ids: list[int] = Field(min_length=1)
    ebay_account_key: str = Field(default="manual", min_length=1, max_length=128)
    action: str = Field(default="create_draft", pattern="^(create_draft|publish)$")
    scheduled_for: datetime | None = None
    listing_schedule_at: datetime | None = None


class ListingJobUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(queued|running|needs_review|ready_to_save|saved_draft|completed|tombstoned|failed|paused|cancelled)$")
    scheduled_for: datetime | None = None
    listing_schedule_at: datetime | None = None
    ebay_draft_id: str | None = Field(default=None, max_length=128)
    listing_id: str | None = Field(default=None, max_length=128)
    message: str | None = None


class ListingDraftVerification(BaseModel):
    exists: bool
    ebay_draft_id: str | None = Field(default=None, max_length=128)
    url: str | None = None
    message: str | None = None


class ListingJobRead(BaseModel):
    id: int
    product_id: int
    sku: str
    title: str
    price: float | None = None
    estimated_profit: float | None = None
    meets_minimum_profit: bool | None = None
    ebay_account_key: str
    action: str
    status: str
    scheduled_for: datetime | None = None
    listing_schedule_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempts: int
    ebay_draft_id: str | None = None
    message: str | None = None
    manual_ready: bool
    api_ready: bool
    missing_manual: list[str]
    missing_api: list[str]
    warnings: list[str]
    image_count: int
    local_image_count: int
    image_upload_status: str
    source_url: str | None = None
    assistant_url: str
    updated_at: datetime
    created_at: datetime


class ListingJobRunResult(BaseModel):
    job: ListingJobRead
    package: EbayListingPackage | None = None


class PriceSnapshotRead(BaseModel):
    id: int
    product_id: int
    source: str
    price: float | None = None
    shipping: float
    floor_price: float | None = None
    suggested_price: float | None = None
    message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RepricingRunRead(BaseModel):
    updated: int
    snapshots: list[PriceSnapshotRead]
    revision_jobs_queued: int = 0
    revision_jobs_updated: int = 0


class RepricingSelectionRequest(BaseModel):
    product_ids: list[int] = Field(min_length=1)


class CatalogAutomationRunRead(BaseModel):
    draft_prices_updated: int
    repricing_snapshots: int
    image_products_checked: int
    image_products_attempted: int
    image_download_attempted: int
    image_downloaded: int


class AutomationRunRead(BaseModel):
    id: int
    task_name: str
    status: str
    draft_prices_updated: int
    repricing_snapshots: int
    image_products_checked: int
    image_products_attempted: int
    image_download_attempted: int
    image_downloaded: int
    message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceRefreshQueueItem(BaseModel):
    product_id: int
    sku: str
    title: str
    source_url: str | None = None
    source_price: float | None = None
    source_shipping: float = 0.0
    draft_price: float | None = None
    estimated_profit: float | None = None
    image_count: int = 0
    last_source_update: datetime | None = None
    age_days: int | None = None
    age_hours: float | None = None
    priority: str
    reason: str
    extension_ready: bool


class SourceRefreshQueueRead(BaseModel):
    stale_after_days: int
    stale_after_hours: float = 6.0
    total: int
    needs_refresh: int
    items: list[SourceRefreshQueueItem]


class SourceMonitoringRunRead(BaseModel):
    stale_after_days: int
    stale_after_hours: float = 6.0
    total: int
    needs_refresh: int
    high_priority: int
    medium_priority: int
    extension_ready: int
    run_id: int
    message: str
    items: list[SourceRefreshQueueItem]


class SourceRefreshBatchCreate(BaseModel):
    limit: int = Field(default=5, ge=1, le=150)
    interval_hours: float = Field(default=6.0, ge=0.25, le=168)
    force: bool = False
    auto_claim: bool = True
    product_ids: list[int] | None = None


class SourceRefreshJobRead(BaseModel):
    id: int
    batch_key: str
    product_id: int
    sku: str
    title: str
    source_url: str
    runner_url: str
    status: str
    attempts: int
    baseline_price: float | None = None
    captured_price: float | None = None
    price_changed: bool
    revision_queued: bool
    message: str | None = None
    scheduled_for: datetime
    lease_expires_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SourceRefreshBatchRead(BaseModel):
    batch_key: str
    requested: int
    queued: int
    due_available: int
    interval_hours: float
    runner_url: str | None = None
    jobs: list[SourceRefreshJobRead]


class SourceRefreshJobFailure(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class StatsTotals(BaseModel):
    catalog_revenue: float
    catalog_cost: float
    catalog_fees: float = 0.0
    expected_profit: float
    imported_products: int
    average_margin_percent: float | None = None
    low_profit_products: int = 0
    source_snapshots: int
    order_revenue: float
    active_listings: int = 0
    listed_value: float = 0.0


class StatsSeriesPoint(BaseModel):
    label: str
    revenue: float = 0.0
    cost: float = 0.0
    fees: float = 0.0
    profit: float = 0.0


class StatsImportPoint(BaseModel):
    label: str
    count: int


class StatsMixItem(BaseModel):
    label: str
    value: int


class StatsTopProduct(BaseModel):
    product_id: int
    sku: str
    title: str
    source_price: float | None = None
    source_shipping: float = 0.0
    draft_price: float | None = None
    expected_profit: float | None = None
    stage: str


class StatsOverviewRead(BaseModel):
    selected_range: str
    grain: str
    selected_account: str
    available_accounts: list[str]
    account_note: str
    totals: StatsTotals
    series: list[StatsSeriesPoint]
    import_series: list[StatsImportPoint]
    shipping_mix: list[StatsMixItem]
    pipeline_mix: list[StatsMixItem]
    listing_readiness_mix: list[StatsMixItem]
    top_products: list[StatsTopProduct]


class OrderItemRead(BaseModel):
    id: int
    product_id: int | None = None
    title: str
    quantity: int
    sale_price: float
    expected_profit: float | None = None

    model_config = ConfigDict(from_attributes=True)


class FulfillmentTaskRead(BaseModel):
    id: int
    order_id: int
    status: str
    note: str | None = None
    exception_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class FulfillmentTaskUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|in_progress|completed|refunded|blocked)$")
    note: str | None = None
    exception_reason: str | None = None


class CustomerUpdateRead(BaseModel):
    id: int
    order_id: int
    event: str
    channel: str
    status: str
    subject: str
    body: str
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerUpdateStatusPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(draft|sent|skipped)$")
    subject: str | None = Field(default=None, max_length=256)
    body: str | None = None


class OrderUpdateDraftRunRead(BaseModel):
    drafted: int
    updates: list[CustomerUpdateRead]


class CustomerMessageImport(BaseModel):
    external_message_id: str = Field(min_length=1, max_length=256)
    direction: str = Field(default="inbound", pattern="^(inbound|outbound)$")
    origin: str = Field(default="buyer", pattern="^(buyer|human|automatic|system)$")
    subject: str = Field(default="", max_length=512)
    body: str = Field(min_length=1)
    sent_at: datetime | None = None


class CustomerConversationImport(BaseModel):
    account_id: str = Field(min_length=1, max_length=128)
    ebay_thread_id: str = Field(min_length=1, max_length=256)
    ebay_order_id: str | None = Field(default=None, max_length=128)
    buyer_username: str = Field(default="", max_length=128)
    subject: str = Field(default="", max_length=512)
    messages: list[CustomerMessageImport] = []


class CustomerMessageCreate(BaseModel):
    body: str = Field(min_length=1)
    subject: str = Field(default="", max_length=512)
    origin: str = Field(default="human", pattern="^(human|automatic)$")
    queue_immediately: bool = True


class CustomerMessageUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(draft|queued|sending|sent|failed|cancelled)$")
    external_message_id: str | None = Field(default=None, max_length=256)
    sent_at: datetime | None = None
    error: str | None = None


class CustomerMessageRead(BaseModel):
    id: int
    conversation_id: int
    external_message_id: str | None = None
    direction: str
    origin: str
    status: str
    subject: str
    body: str
    sent_at: datetime | None = None
    attempts: int
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerConversationRead(BaseModel):
    id: int
    account_id: str
    ebay_thread_id: str
    order_id: int | None = None
    buyer_username: str
    buyer_first_name: str = ""
    subject: str
    status: str
    last_message_at: datetime | None = None
    messages: list[CustomerMessageRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerTemplateRead(BaseModel):
    number: int
    key: str
    category: str
    title: str
    body: str
    placeholders: list[str] = []
    automation: str
    requires_review: bool
    review_note: str = ""


class CustomerTemplateRenderRequest(BaseModel):
    variables: dict[str, str] = {}


class CustomerTemplateRenderRead(CustomerTemplateRead):
    rendered_body: str
    unresolved_placeholders: list[str] = []


class CustomerTemplateMessageCreate(CustomerTemplateRenderRequest):
    subject: str = Field(default="", max_length=512)
    queue_immediately: bool = True
    origin: str = Field(default="human", pattern="^(human|automatic)$")


class GiftCardCreate(BaseModel):
    supplier: str = Field(default="home_depot", min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    last_four: str = Field(default="", max_length=4)
    face_value: float = Field(ge=0)
    acquisition_cost: float = Field(ge=0)
    current_balance: float | None = Field(default=None, ge=0)
    secret_ref: str = Field(default="", max_length=256)
    notes: str | None = None


class GiftCardUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    current_balance: float | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern="^(active|depleted|disabled)$")
    secret_ref: str | None = Field(default=None, max_length=256)
    notes: str | None = None


class GiftCardRead(BaseModel):
    id: int
    supplier: str
    label: str
    last_four: str
    face_value: float
    acquisition_cost: float
    current_balance: float
    status: str
    secret_ref: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GiftCardCredentialWrite(BaseModel):
    card_number: str = Field(min_length=8, max_length=64)
    pin: str = Field(min_length=3, max_length=32)


class GiftCardCredentialStatus(BaseModel):
    stored: bool
    secret_ref: str
    last_four: str


class SupplierOrderItemRead(BaseModel):
    id: int
    order_item_id: int | None = None
    product_id: int | None = None
    title: str
    quantity: int
    unit_price: float
    source_url: str

    model_config = ConfigDict(from_attributes=True)


class SupplierOrderPrepare(BaseModel):
    gift_card_id: int | None = None
    recipient_name: str = Field(default="", max_length=256)
    address_line1: str = Field(default="", max_length=256)
    address_line2: str = Field(default="", max_length=256)
    city: str = Field(default="", max_length=128)
    state: str = Field(default="", max_length=64)
    postal_code: str = Field(default="", max_length=32)
    phone: str = Field(default="", max_length=64)


class SupplierOrderUpdate(BaseModel):
    status: str | None = Field(
        default=None,
        pattern="^(draft|needs_review|queued|placing|placed|shipped|delivered|failed|cancelled)$",
    )
    external_order_id: str | None = Field(default=None, max_length=128)
    item_subtotal: float | None = Field(default=None, ge=0)
    sales_tax: float | None = Field(default=None, ge=0)
    shipping_cost: float | None = Field(default=None, ge=0)
    gift_card_amount: float | None = Field(default=None, ge=0)
    card_amount: float | None = Field(default=None, ge=0)
    total: float | None = Field(default=None, ge=0)
    tracking_number: str | None = Field(default=None, max_length=256)
    carrier: str | None = Field(default=None, max_length=128)
    estimated_delivery: datetime | None = None
    failure_reason: str | None = None
    recipient_name: str | None = Field(default=None, max_length=256)
    address_line1: str | None = Field(default=None, max_length=256)
    address_line2: str | None = Field(default=None, max_length=256)
    city: str | None = Field(default=None, max_length=128)
    state: str | None = Field(default=None, max_length=64)
    postal_code: str | None = Field(default=None, max_length=32)
    phone: str | None = Field(default=None, max_length=64)


class SupplierOrderRead(BaseModel):
    id: int
    order_id: int
    gift_card_id: int | None = None
    supplier: str
    status: str
    source_url: str
    external_order_id: str
    payment_method: str
    item_subtotal: float
    sales_tax: float
    shipping_cost: float
    gift_card_amount: float
    card_amount: float
    total: float
    tracking_number: str
    carrier: str
    estimated_delivery: datetime | None = None
    approval_required: bool
    approved_total: float
    approved_at: datetime | None = None
    placed_at: datetime | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    attempts: int
    failure_reason: str | None = None
    recipient_name: str
    address_line1: str
    address_line2: str
    city: str
    state: str
    postal_code: str
    phone: str
    items: list[SupplierOrderItemRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupplierOrderClaimRead(SupplierOrderRead):
    checkout_token: str


class SupplierCheckoutCredentialRead(BaseModel):
    supplier_order_id: int
    card_number: str
    pin: str
    approved_total: float
    current_balance: float


class FinancialAccountUpsert(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=256)
    account_type: str = Field(pattern="^(bank|credit_card|ebay|gift_card|other)$")
    name: str = Field(min_length=1, max_length=256)
    mask: str = Field(default="", max_length=8)
    currency: str = Field(default="USD", max_length=8)
    current_balance: float = 0.0
    available_balance: float | None = None
    held_balance: float | None = None
    estimated_release_at: datetime | None = None
    status: str = Field(default="connected", pattern="^(connected|stale|error|disabled)$")
    connection_ref: str = Field(default="", max_length=256)
    last_synced_at: datetime | None = None


class FinancialAccountRead(FinancialAccountUpsert):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionExpenseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    amount: float = Field(ge=0)
    cadence: str = Field(default="monthly", pattern="^(weekly|monthly|annual)$")
    next_charge_at: datetime | None = None
    payment_account_id: int | None = None
    category: str = Field(default="software", max_length=64)
    status: str = Field(default="active", pattern="^(active|paused|cancelled)$")
    notes: str | None = None


class SubscriptionExpenseRead(SubscriptionExpenseCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FinanceEntryImport(BaseModel):
    provider: str = Field(default="manual", max_length=64)
    external_id: str = Field(min_length=1, max_length=256)
    financial_account_id: int | None = None
    entry_type: str = Field(pattern="^(income|expense|fee|refund|payout)$")
    category: str = Field(max_length=64)
    amount: float
    description: str = Field(default="", max_length=512)
    occurred_at: datetime


class ProfitLossPeriodRead(BaseModel):
    period: str
    revenue: float
    supplier_cost: float
    operating_expenses: float
    profit: float
    orders: int


class FinanceOverviewRead(BaseModel):
    revenue: float
    supplier_cost: float
    operating_expenses: float
    profit: float
    gift_card_face_balance: float
    gift_card_cash_basis: float
    bank_balance: float
    credit_card_balance: float
    ebay_available: float
    ebay_held: float
    accounts: list[FinancialAccountRead]
    subscriptions: list[SubscriptionExpenseRead]
    periods: list[ProfitLossPeriodRead]


class OrderRead(BaseModel):
    id: int
    ebay_order_id: str
    account_id: str = "sandbox"
    buyer_username: str | None = None
    recipient_name: str = ""
    status: str
    ship_by: datetime | None = None
    total: float
    items: list[OrderItemRead] = []
    fulfillment_tasks: list[FulfillmentTaskRead] = []
    customer_updates: list[CustomerUpdateRead] = []
    supplier_orders: list[SupplierOrderRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EbayOrderReportImport(BaseModel):
    account_key: str = Field(default="manual", min_length=1, max_length=128)
    run_id: int | None = None
    filename: str = Field(default="ebay-orders.csv", max_length=1000)
    report_base64: str = Field(min_length=1)


class EbayOrderReportImportResult(BaseModel):
    orders_seen: int
    orders_upserted: int
    unmatched_items: int
    run_id: int | None = None


class SettingsRead(BaseModel):
    ebay_environment: str
    ebay_enable_writes: bool
    ebay_client_id: str = ""
    ebay_redirect_uri: str = ""
    ebay_refresh_token: str = ""
    ebay_refresh_token_expires_at: str = ""
    ebay_access_token: str = ""
    ebay_token_expires_at: str = ""
    default_ebay_fee_rate: float
    default_promoted_rate: float
    default_return_risk_rate: float
    default_undercut_amount: float
    default_min_profit: float
    default_min_profit_guard_enabled: bool = False
    default_gift_card_discount_enabled: bool = False
    default_gift_card_discount_percent: float = 6.0
    default_sales_tax_percent: float = 0.0
    default_risk_buffer: float
    default_margin_percent: float = 0.20
    source_refresh_interval_days: float = 7.0
    source_refresh_interval_hours: float = 6.0
    source_refresh_auto_enabled: bool = True
    source_refresh_auto_batch_size: float = 5.0
    source_refresh_auto_poll_minutes: float = 5.0
    ebay_revision_auto_approve_enabled: bool = False
    ebay_revision_max_change_percent: float = 25.0
    ebay_revision_execution_mode: str = "bulk_upload"
    default_pricing_strategy: str = "margin"
    default_round_to_99: bool = False
    default_rounding_cents: float = 0.99
    default_offers_enabled: bool = False
    default_listing_schedule_mode: str = "now"
    default_listing_schedule_days_ahead: float = 0.0
    default_listing_schedule_time: str = "09:00"
    display_timezone: str = "America/New_York"
    auto_delist_zero_view_enabled: bool = False
    auto_delist_zero_view_days: float = 25.0
    default_vero_remove_brand_from_title: bool = True
    default_strip_brand_from_title: bool = True
    default_title_suffix: str = " | FREE SHIPPING"
    default_item_condition: str = "New"
    default_shipping_cost_type: str = "flat"
    default_domestic_shipping_service: str = "Economy Shipping"
    default_buyer_shipping_cost: float = 0.0
    ebay_marketplace_id: str = "EBAY_US"
    ebay_category_id: str = ""
    ebay_merchant_location_key: str = ""
    ebay_fulfillment_policy_id: str = ""
    ebay_payment_policy_id: str = ""
    ebay_return_policy_id: str = ""
    ebay_expected_username: str = ""
    ui_theme: str = Field(default="system", pattern="^(system|light|dark)$")
    supplier_settings_json: str = "{}"
    description_template_enabled: bool = True
    description_template_name: str = "AutoZS Home Improvement"
    description_template_brand: str = "AutoZS"
    description_template_about: str = ""
    description_template_shipping: str = ""
    description_template_returns: str = ""
    description_template_satisfaction: str = ""
    keyword_blacklist_json: str = "[]"
    buyer_accounts_json: str = "[]"
    marketing_settings_json: str = "{}"
    notifications_order_updates: bool = True
    notifications_listing_errors: bool = True
    notifications_email: str = ""


class PricingSettingsUpdate(BaseModel):
    ebay_environment: str | None = Field(default=None, pattern="^(sandbox|production)$")
    ebay_enable_writes: bool | None = None
    ebay_client_id: str | None = None
    ebay_client_secret: str | None = None
    ebay_redirect_uri: str | None = None
    ebay_refresh_token: str | None = None
    ebay_refresh_token_expires_at: str | None = None
    ebay_access_token: str | None = None
    ebay_token_expires_at: str | None = None
    default_ebay_fee_rate: float | None = Field(default=None, ge=0, lt=1)
    default_promoted_rate: float | None = Field(default=None, ge=0, lt=1)
    default_return_risk_rate: float | None = Field(default=None, ge=0, lt=1)
    default_undercut_amount: float | None = Field(default=None, ge=0)
    default_min_profit: float | None = Field(default=None, ge=0)
    default_min_profit_guard_enabled: bool | None = None
    default_gift_card_discount_enabled: bool | None = None
    default_gift_card_discount_percent: float | None = Field(default=None, ge=0, le=100)
    default_sales_tax_percent: float | None = Field(default=None, ge=0, le=100)
    default_risk_buffer: float | None = Field(default=None, ge=0)
    default_margin_percent: float | None = Field(default=None, ge=0, lt=10)
    source_refresh_interval_days: float | None = Field(default=None, ge=1, le=90)
    source_refresh_interval_hours: float | None = Field(default=None, ge=0.25, le=168)
    source_refresh_auto_enabled: bool | None = None
    source_refresh_auto_batch_size: float | None = Field(default=None, ge=1, le=150)
    source_refresh_auto_poll_minutes: float | None = Field(default=None, ge=1, le=120)
    ebay_revision_auto_approve_enabled: bool | None = None
    ebay_revision_max_change_percent: float | None = Field(default=None, ge=0.1, le=100)
    ebay_revision_execution_mode: str | None = Field(default=None, pattern="^(bulk_upload|browser_fallback)$")
    default_pricing_strategy: str | None = Field(
        default=None, pattern="^(margin|competitor|safe_competitor|breakeven)$"
    )
    default_round_to_99: bool | None = None
    default_rounding_cents: float | None = Field(default=None, ge=0, lt=1)
    default_offers_enabled: bool | None = None
    default_listing_schedule_mode: str | None = Field(default=None, pattern="^(now|scheduled)$")
    default_listing_schedule_days_ahead: float | None = Field(default=None, ge=0, le=30)
    default_listing_schedule_time: str | None = Field(default=None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
    display_timezone: str | None = Field(
        default=None,
        pattern="^(America/New_York|America/Chicago|America/Denver|America/Los_Angeles|UTC)$",
    )
    auto_delist_zero_view_enabled: bool | None = None
    auto_delist_zero_view_days: float | None = Field(default=None, ge=1, le=365)
    default_vero_remove_brand_from_title: bool | None = None
    default_strip_brand_from_title: bool | None = None
    default_title_suffix: str | None = Field(default=None, max_length=40)
    default_item_condition: str | None = Field(default=None, max_length=40)
    default_shipping_cost_type: str | None = Field(default=None, pattern="^(flat|calculated)$")
    default_domestic_shipping_service: str | None = Field(default=None, max_length=80)
    default_buyer_shipping_cost: float | None = Field(default=None, ge=0, le=500)
    ebay_marketplace_id: str | None = None
    ebay_category_id: str | None = None
    ebay_merchant_location_key: str | None = None
    ebay_fulfillment_policy_id: str | None = None
    ebay_payment_policy_id: str | None = None
    ebay_return_policy_id: str | None = None
    ebay_expected_username: str | None = Field(default=None, max_length=128)


class UiThemeUpdate(BaseModel):
    ui_theme: str = Field(pattern="^(system|light|dark)$")


class CatalogSettingsUpdate(BaseModel):
    supplier_settings_json: str | None = Field(default=None, max_length=12000)
    description_template_enabled: bool | None = None
    description_template_name: str | None = Field(default=None, max_length=120)
    description_template_brand: str | None = Field(default=None, max_length=80)
    description_template_about: str | None = Field(default=None, max_length=3000)
    description_template_shipping: str | None = Field(default=None, max_length=3000)
    description_template_returns: str | None = Field(default=None, max_length=3000)
    description_template_satisfaction: str | None = Field(default=None, max_length=3000)
    keyword_blacklist_json: str | None = Field(default=None, max_length=12000)
    buyer_accounts_json: str | None = Field(default=None, max_length=24000)
    marketing_settings_json: str | None = Field(default=None, max_length=24000)
    notifications_order_updates: bool | None = None
    notifications_listing_errors: bool | None = None
    notifications_email: str | None = Field(default=None, max_length=320)


class EbayConnectionStatus(BaseModel):
    environment: str
    configured: bool
    connected: bool
    writes_enabled: bool
    missing: list[str]
    auth_url: str | None = None
    scopes: list[str]
    api_base_url: str
    token_url: str
    account_label: str


class WorkerRead(BaseModel):
    id: int
    worker_id: str
    label: str
    role: str
    platform: str = ""
    status: str
    api_url: str = ""
    database_url: str = ""
    chrome_executable_path: str = ""
    chrome_profile_root: str = ""
    ebay_profile_root: str = ""
    home_depot_profile_root: str = ""
    last_seen_at: datetime | None = None
    last_checked_at: datetime | None = None
    seconds_since_seen: int | None = None
    message: str = ""
    created_at: datetime
    updated_at: datetime


class OperationalAlertRead(BaseModel):
    id: int
    key: str
    severity: str
    source: str
    status: str
    title: str
    message: str = ""
    product_id: int | None = None
    listing_id: int | None = None
    job_type: str | None = None
    job_id: int | None = None
    action_url: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    last_notified_at: datetime | None = None
    resolved_at: datetime | None = None
    dismissed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OperationalAlertUpdate(BaseModel):
    status: str = Field(pattern="^(open|acknowledged|resolved|dismissed)$")


class OperationalAlertSummary(BaseModel):
    open: int
    acknowledged: int
    resolved: int
    dismissed: int
    critical: int
    warning: int
    info: int
    active: int


class PushConfigRead(BaseModel):
    enabled: bool
    public_key: str = ""
    reason: str = ""
    subject: str = ""


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: dict[str, str]
    label: str | None = None
    user_agent: str | None = None
    dashboard_url: str | None = None
    vapid_public_key: str | None = None
    preferences: dict[str, bool | str | int] | None = None


class PushSubscriptionUpdate(BaseModel):
    enabled: bool | None = None
    preferences: dict[str, bool | str | int] | None = None
    timezone: str | None = Field(default=None, max_length=64)
    weekly_summary_day: int | None = Field(default=None, ge=0, le=6)
    weekly_summary_time: str | None = Field(default=None, pattern="^(?:[01]\\d|2[0-3]):[0-5]\\d$")
    weekly_summary_enabled: bool | None = None


class PushSubscriptionRead(BaseModel):
    id: int
    endpoint: str
    label: str = ""
    dashboard_url: str = ""
    vapid_public_key: str = ""
    preferences: dict[str, bool | str | int] = Field(default_factory=dict)
    timezone: str = "America/New_York"
    weekly_summary_day: int = 5
    weekly_summary_time: str = "18:00"
    weekly_summary_enabled: bool = True
    enabled: bool
    last_seen_at: datetime
    last_notified_at: datetime | None = None
    last_weekly_summary_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PushTestRequest(BaseModel):
    title: str = "AutoZS test alert"
    body: str = "Push notifications are working."
    subscription_id: int | None = None


class PushSaleTestRequest(BaseModel):
    subscription_id: int


class PushDispatchResult(BaseModel):
    attempted: int = 0
    sent: int = 0
    failed: int = 0
    notified_alerts: int = 0
    message: str = ""


class EbayAccountRead(BaseModel):
    id: int
    key: str
    label: str
    account_id: str
    environment: str
    marketplace_id: str = "EBAY_US"
    writes_enabled: bool = False
    configured: bool
    connected: bool
    missing: list[str] = []
    client_id: str = ""
    redirect_uri: str = ""
    access_token: str = ""
    refresh_token: str = ""
    token_expires_at: str = ""
    refresh_token_expires_at: str = ""
    category_id: str = ""
    merchant_location_key: str = ""
    fulfillment_policy_id: str = ""
    payment_policy_id: str = ""
    return_policy_id: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EbayAccountUpsert(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    key: str | None = Field(default=None, max_length=128)
    account_id: str | None = Field(default=None, max_length=128)
    environment: str = Field(default="production", pattern="^(sandbox|production)$")
    marketplace_id: str = "EBAY_US"
    writes_enabled: bool = False
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: str | None = None
    refresh_token_expires_at: str | None = None
    category_id: str | None = None
    merchant_location_key: str | None = None
    fulfillment_policy_id: str | None = None
    payment_policy_id: str | None = None
    return_policy_id: str | None = None


class EbayBrowserAccountReport(BaseModel):
    detected_username: str | None = Field(default=None, max_length=128)
    url: str | None = Field(default=None, max_length=1000)
    marketplace: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default="chrome-extension", max_length=64)
    account_key: str = Field(default="manual", max_length=128)


class EbayBrowserAccountStatus(BaseModel):
    account_key: str
    expected_username: str = ""
    detected_username: str = ""
    detected_at: str = ""
    url: str = ""
    marketplace: str = ""
    source: str = ""
    configured: bool
    matched: bool
    can_list: bool
    message: str


class ListingAutomationPauseUpdate(BaseModel):
    paused: bool
    reason: str | None = Field(default=None, max_length=500)


class ListingAutomationPauseStatus(BaseModel):
    paused: bool
    reason: str = ""
    changed_at: str = ""


class EbayOAuthStartRead(BaseModel):
    authorization_url: str
    state: str
    scopes: list[str]
    environment: str


class EbayOAuthCallbackRequest(BaseModel):
    code: str
    state: str | None = None


class EbayOAuthTokenRead(BaseModel):
    environment: str
    connected: bool
    token_type: str
    access_token_expires_at: str
    refresh_token_expires_at: str | None = None
    scopes: list[str]

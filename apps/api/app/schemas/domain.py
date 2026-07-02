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
    in_stock: bool = True


class SupplierRead(BaseModel):
    id: int
    supplier: str
    source_url: str
    supplier_sku: str | None = None
    last_price: float | None = None
    last_shipping: float
    subscription_discount_percent: float | None = None
    in_stock: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductImageRead(BaseModel):
    id: int
    image_url: str
    local_path: str | None = None
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


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


class CapturedProductUpdate(BaseModel):
    title: str | None = None
    source_price: float | None = Field(default=None, ge=0)
    source_shipping: float | None = Field(default=None, ge=0)
    competitor_price: float | None = Field(default=None, ge=0)
    subscription_discount_percent: float | None = Field(default=None, ge=0, le=100)
    description: str | None = None
    image_urls: str | None = None


class CapturedProductImport(BaseModel):
    source_url: str
    title: str
    source_price: float | None = Field(default=None, ge=0)
    source_shipping: float | None = Field(default=None, ge=0)
    competitor_price: float | None = Field(default=None, ge=0)
    subscription_discount_percent: float | None = Field(default=None, ge=0, le=100)
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
    source_shipping: float = 0.0
    landed_cost: float | None = None
    effective_source_cost: float | None = None
    gift_card_discount_enabled: bool = False
    gift_card_discount_percent: float = 0.0
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
    days_until_relist: int | None = None
    auto_delist_candidate: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EbayListingMarkRequest(BaseModel):
    listing_id: str | None = None
    account_id: str = "manual"
    environment: str = "manual"
    quantity: int = Field(default=1, ge=0)
    status: str = "listed"


class EbaySyncRunCreate(BaseModel):
    account_key: str = Field(default="manual", min_length=1, max_length=128)
    source: str = Field(default="seller_hub_report", max_length=64)


class EbaySyncRunProgress(BaseModel):
    phase: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=32)
    message: str | None = Field(default=None, max_length=2000)
    report_reference: str | None = Field(default=None, max_length=128)
    report_filename: str | None = Field(default=None, max_length=1000)
    increment_attempts: bool = False


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


class EbayRevisionEnqueueResult(BaseModel):
    queued: int
    updated: int


class EbayRevisionJobUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(queued|running|completed|failed|paused|cancelled)$")
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
    status: str | None = Field(default=None, pattern="^(open|in_progress|completed|blocked)$")
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


class OrderRead(BaseModel):
    id: int
    ebay_order_id: str
    account_id: str = "sandbox"
    buyer_username: str | None = None
    status: str
    ship_by: datetime | None = None
    total: float
    items: list[OrderItemRead] = []
    fulfillment_tasks: list[FulfillmentTaskRead] = []
    customer_updates: list[CustomerUpdateRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    default_risk_buffer: float
    default_margin_percent: float = 0.20
    source_refresh_interval_days: float = 7.0
    source_refresh_interval_hours: float = 6.0
    source_refresh_auto_enabled: bool = True
    source_refresh_auto_batch_size: float = 5.0
    source_refresh_auto_poll_minutes: float = 5.0
    default_pricing_strategy: str = "margin"
    default_round_to_99: bool = False
    default_rounding_cents: float = 0.99
    default_offers_enabled: bool = False
    default_listing_schedule_mode: str = "now"
    default_listing_schedule_days_ahead: float = 0.0
    default_listing_schedule_time: str = "09:00"
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
    default_risk_buffer: float | None = Field(default=None, ge=0)
    default_margin_percent: float | None = Field(default=None, ge=0, lt=10)
    source_refresh_interval_days: float | None = Field(default=None, ge=1, le=90)
    source_refresh_interval_hours: float | None = Field(default=None, ge=0.25, le=168)
    source_refresh_auto_enabled: bool | None = None
    source_refresh_auto_batch_size: float | None = Field(default=None, ge=1, le=150)
    source_refresh_auto_poll_minutes: float | None = Field(default=None, ge=1, le=120)
    default_pricing_strategy: str | None = Field(default=None, pattern="^(margin|competitor|safe_competitor)$")
    default_round_to_99: bool | None = None
    default_rounding_cents: float | None = Field(default=None, ge=0, lt=1)
    default_offers_enabled: bool | None = None
    default_listing_schedule_mode: str | None = Field(default=None, pattern="^(now|scheduled)$")
    default_listing_schedule_days_ahead: float | None = Field(default=None, ge=0, le=30)
    default_listing_schedule_time: str | None = Field(default=None, pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$")
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

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResearchSource(str, Enum):
    competitor = "competitor"
    keyword = "keyword"


class CandidateStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ProductStatus(str, Enum):
    draft = "draft"
    monitoring = "monitoring"
    paused = "paused"
    deleted = "deleted"


class FulfillmentStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"


class CustomerUpdateStatus(str, Enum):
    draft = "draft"
    sent = "sent"
    skipped = "skipped"


class ListingJobStatus(str, Enum):
    queued = "queued"
    running = "running"
    needs_review = "needs_review"
    ready_to_save = "ready_to_save"
    saved_draft = "saved_draft"
    completed = "completed"
    tombstoned = "tombstoned"
    failed = "failed"
    paused = "paused"
    cancelled = "cancelled"


class ListingJobAction(str, Enum):
    create_draft = "create_draft"
    publish = "publish"


class EbayRevisionJobStatus(str, Enum):
    needs_review = "needs_review"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    paused = "paused"
    cancelled = "cancelled"


class EbayRevisionBatchStatus(str, Enum):
    prepared = "prepared"
    uploading = "uploading"
    waiting_results = "waiting_results"
    completed = "completed"
    needs_review = "needs_review"
    failed = "failed"
    cancelled = "cancelled"


class SourceRefreshJobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class EbaySyncRunStatus(str, Enum):
    queued = "queued"
    running = "running"
    needs_review = "needs_review"
    completed = "completed"
    failed = "failed"


class WorkerStatus(str, Enum):
    online = "online"
    stale = "stale"
    offline = "offline"


class SnapshotSource(str, Enum):
    supplier = "supplier"
    competitor = "competitor"
    calculated = "calculated"


class Competitor(Base, TimestampMixin):
    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    seed_listing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchJob(Base, TimestampMixin):
    __tablename__ = "research_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    query: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class CandidateProduct(Base, TimestampMixin):
    __tablename__ = "candidate_products"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_candidate_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(512))
    listing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitor_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_sold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seller_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=CandidateStatus.pending.value)
    research_job_id: Mapped[int | None] = mapped_column(ForeignKey("research_jobs.id"), nullable=True)


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default=ProductStatus.draft.value)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidate_products.id"), nullable=True)
    competitor_listing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitor_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    desired_profit: Mapped[float] = mapped_column(Float, default=8.0)
    risk_buffer: Mapped[float] = mapped_column(Float, default=3.0)
    fixed_costs: Mapped[float] = mapped_column(Float, default=0.0)
    ebay_fee_rate: Mapped[float] = mapped_column(Float, default=0.1325)
    promoted_rate: Mapped[float] = mapped_column(Float, default=0.0)
    return_risk_rate: Mapped[float] = mapped_column(Float, default=0.02)
    undercut_amount: Mapped[float] = mapped_column(Float, default=0.20)
    listing_schedule_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    supplier_products: Mapped[list["SupplierProduct"]] = relationship(back_populates="product")
    images: Mapped[list["ProductImage"]] = relationship(back_populates="product")
    listing_drafts: Mapped[list["ListingDraft"]] = relationship(back_populates="product")
    listing_jobs: Mapped[list["ListingJob"]] = relationship(back_populates="product")


class SupplierProduct(Base, TimestampMixin):
    __tablename__ = "supplier_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    supplier: Mapped[str] = mapped_column(String(64), default="home_depot")
    source_url: Mapped[str] = mapped_column(Text)
    supplier_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_shipping: Mapped[float] = mapped_column(Float, default=0.0)
    subscription_discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped[Product] = relationship(back_populates="supplier_products")


class ProductImage(Base, TimestampMixin):
    __tablename__ = "product_images"
    __table_args__ = (UniqueConstraint("product_id", "image_url", name="uq_product_image_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    image_url: Mapped[str] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="images")


class ListingDraft(Base, TimestampMixin):
    __tablename__ = "listing_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    marketplace: Mapped[str] = mapped_column(String(32), default="ebay")
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text)
    source_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    calculated_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_percent: Mapped[float] = mapped_column(Float, default=0.20)
    ebay_fee_rate: Mapped[float] = mapped_column(Float, default=0.1325)
    status: Mapped[str] = mapped_column(String(32), default="draft")

    product: Mapped[Product] = relationship(back_populates="listing_drafts")


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)


class EbayAccount(Base, TimestampMixin):
    __tablename__ = "ebay_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(128))
    account_id: Mapped[str] = mapped_column(String(128), index=True)
    environment: Mapped[str] = mapped_column(String(32), default="production")
    marketplace_id: Mapped[str] = mapped_column(String(32), default="EBAY_US")
    client_id: Mapped[str] = mapped_column(Text, default="")
    client_secret: Mapped[str] = mapped_column(Text, default="")
    redirect_uri: Mapped[str] = mapped_column(Text, default="")
    access_token: Mapped[str] = mapped_column(Text, default="")
    refresh_token: Mapped[str] = mapped_column(Text, default="")
    token_expires_at: Mapped[str] = mapped_column(Text, default="")
    refresh_token_expires_at: Mapped[str] = mapped_column(Text, default="")
    oauth_state: Mapped[str] = mapped_column(Text, default="")
    writes_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    category_id: Mapped[str] = mapped_column(String(128), default="")
    merchant_location_key: Mapped[str] = mapped_column(String(128), default="")
    fulfillment_policy_id: Mapped[str] = mapped_column(String(128), default="")
    payment_policy_id: Mapped[str] = mapped_column(String(128), default="")
    return_policy_id: Mapped[str] = mapped_column(String(128), default="")


class EbayListing(Base, TimestampMixin):
    __tablename__ = "ebay_listings"
    __table_args__ = (UniqueConstraint("account_id", "listing_id", name="uq_ebay_listing_account_listing"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    listing_id: Mapped[str] = mapped_column(String(128), index=True)
    account_id: Mapped[str] = mapped_column(String(128), default="sandbox")
    environment: Mapped[str] = mapped_column(String(32), default="sandbox")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    renews_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    view_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    views_measured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EbayListingViewSnapshot(Base):
    __tablename__ = "ebay_listing_view_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ebay_listing_id: Mapped[int] = mapped_column(ForeignKey("ebay_listings.id"), index=True)
    sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("ebay_sync_runs.id"), nullable=True, index=True)
    views: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class WorkerNode(Base, TimestampMixin):
    __tablename__ = "workers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(64), default="operations")
    platform: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default=WorkerStatus.online.value, index=True)
    api_url: Mapped[str] = mapped_column(Text, default="")
    database_url: Mapped[str] = mapped_column(Text, default="")
    chrome_executable_path: Mapped[str] = mapped_column(Text, default="")
    chrome_profile_root: Mapped[str] = mapped_column(Text, default="")
    ebay_profile_root: Mapped[str] = mapped_column(Text, default="")
    home_depot_profile_root: Mapped[str] = mapped_column(Text, default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class EbaySyncRun(Base, TimestampMixin):
    __tablename__ = "ebay_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_key: Mapped[str] = mapped_column(String(128), default="manual", index=True)
    status: Mapped[str] = mapped_column(String(32), default=EbaySyncRunStatus.queued.value, index=True)
    phase: Mapped[str] = mapped_column(String(64), default="queued")
    source: Mapped[str] = mapped_column(String(64), default="seller_hub_report")
    report_type: Mapped[str] = mapped_column(String(64), default="active_listings")
    report_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    report_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    listings_seen: Mapped[int] = mapped_column(Integer, default=0)
    listings_upserted: Mapped[int] = mapped_column(Integer, default=0)
    listings_imported: Mapped[int] = mapped_column(Integer, default=0)
    listings_tombstoned: Mapped[int] = mapped_column(Integer, default=0)
    orders_seen: Mapped[int] = mapped_column(Integer, default=0)
    orders_upserted: Mapped[int] = mapped_column(Integer, default=0)
    revision_jobs_queued: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class EbayRevisionJob(Base, TimestampMixin):
    __tablename__ = "ebay_revision_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    ebay_listing_id: Mapped[int] = mapped_column(ForeignKey("ebay_listings.id"), index=True)
    ebay_account_key: Mapped[str] = mapped_column(String(128), default="manual", index=True)
    action: Mapped[str] = mapped_column(String(32), default="revise_price", index=True)
    status: Mapped[str] = mapped_column(String(32), default=EbayRevisionJobStatus.needs_review.value, index=True)
    old_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price: Mapped[float] = mapped_column(Float)
    source_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_shipping: Mapped[float] = mapped_column(Float, default=0.0)
    projected_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    minimum_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    guard_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    guard_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class EbayRevisionTemplate(Base, TimestampMixin):
    __tablename__ = "ebay_revision_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    filename: Mapped[str] = mapped_column(Text, default="")
    template_csv: Mapped[str] = mapped_column(Text)


class EbayRevisionBatch(Base, TimestampMixin):
    __tablename__ = "ebay_revision_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_key: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default=EbayRevisionBatchStatus.prepared.value, index=True)
    job_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    filename: Mapped[str] = mapped_column(Text)
    csv_content: Mapped[str] = mapped_column(Text)
    result_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ListingJob(Base, TimestampMixin):
    __tablename__ = "listing_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    ebay_account_key: Mapped[str] = mapped_column(String(128), default="manual", index=True)
    action: Mapped[str] = mapped_column(String(32), default=ListingJobAction.create_draft.value, index=True)
    status: Mapped[str] = mapped_column(String(32), default=ListingJobStatus.queued.value, index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    listing_schedule_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ebay_draft_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped[Product] = relationship(back_populates="listing_jobs")


class PriceSnapshot(Base, TimestampMixin):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipping: Mapped[float] = mapped_column(Float, default=0.0)
    floor_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggested_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceRefreshJob(Base, TimestampMixin):
    __tablename__ = "source_refresh_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_key: Mapped[str] = mapped_column(String(64), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default=SourceRefreshJobStatus.queued.value, index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    baseline_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    revision_queued: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AutomationRun(Base, TimestampMixin):
    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_name: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    draft_prices_updated: Mapped[int] = mapped_column(Integer, default=0)
    repricing_snapshots: Mapped[int] = mapped_column(Integer, default=0)
    image_products_checked: Mapped[int] = mapped_column(Integer, default=0)
    image_products_attempted: Mapped[int] = mapped_column(Integer, default=0)
    image_download_attempted: Mapped[int] = mapped_column(Integer, default=0)
    image_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ebay_order_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    account_id: Mapped[str] = mapped_column(String(128), default="sandbox")
    buyer_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="imported")
    ship_by: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total: Mapped[float] = mapped_column(Float, default=0.0)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    fulfillment_tasks: Mapped[list["FulfillmentTask"]] = relationship(back_populates="order")
    customer_updates: Mapped[list["CustomerUpdate"]] = relationship(back_populates="order")


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    sale_price: Mapped[float] = mapped_column(Float, default=0.0)
    expected_profit: Mapped[float | None] = mapped_column(Float, nullable=True)

    order: Mapped[Order] = relationship(back_populates="items")


class FulfillmentTask(Base, TimestampMixin):
    __tablename__ = "fulfillment_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default=FulfillmentStatus.open.value)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped[Order] = relationship(back_populates="fulfillment_tasks")


class CustomerUpdate(Base, TimestampMixin):
    __tablename__ = "customer_updates"
    __table_args__ = (UniqueConstraint("order_id", "event", name="uq_customer_update_order_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    event: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="ebay_message")
    status: Mapped[str] = mapped_column(String(32), default=CustomerUpdateStatus.draft.value, index=True)
    subject: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    order: Mapped[Order] = relationship(back_populates="customer_updates")

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DepopAccountUpsert(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,127}$")
    label: str = Field(min_length=1, max_length=128)
    username: str = Field(default="", max_length=128)
    chrome_profile_root: str = ""
    enabled: bool = True
    writes_enabled: bool = False


class DepopAccountRead(DepopAccountUpsert):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DepopVariantCreate(BaseModel):
    product_id: int
    account_key: str
    variant_key: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    description: str = ""
    price: float = Field(gt=0, allow_inf_nan=False)
    image_ids: list[int] = Field(default_factory=list, max_length=4)
    size: str = ""
    brand: str = ""
    category: str = ""
    condition: str = "Brand new"
    color: str = ""
    shipping_method: str = ""
    packed_weight_lb: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    supplier_weight_lb: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class DepopVariantUpdate(BaseModel):
    account_key: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{1,127}$")
    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None
    price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    image_ids: list[int] | None = Field(default=None, max_length=4)
    size: str | None = None
    brand: str | None = None
    category: str | None = None
    condition: str | None = None
    color: str | None = None
    shipping_method: str | None = None
    packed_weight_lb: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    supplier_weight_lb: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    status: str | None = None
    depop_listing_id: str | None = None
    published_at: datetime | None = None
    views_count: int | None = Field(default=None, ge=0)
    clicks_count: int | None = Field(default=None, ge=0)
    likes_count: int | None = Field(default=None, ge=0)
    bags_count: int | None = Field(default=None, ge=0)
    offers_count: int | None = Field(default=None, ge=0)
    metrics_synced_at: datetime | None = None


class DepopVariantRead(BaseModel):
    id: int
    product_id: int
    account_key: str
    variant_key: str
    title: str
    description: str
    price: float
    image_ids: list[int]
    size: str
    brand: str
    category: str
    condition: str
    color: str
    shipping_method: str
    packed_weight_lb: float | None = None
    supplier_weight_lb: float | None = None
    status: str
    depop_listing_id: str | None = None
    published_at: datetime | None = None
    views_count: int = 0
    clicks_count: int = 0
    likes_count: int = 0
    bags_count: int = 0
    offers_count: int = 0
    metrics_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AmazonVariationIn(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    asin: str = Field(default="", max_length=32)
    image_url: str
    thumb_url: str = ""


class AmazonReviewPhotoIn(BaseModel):
    image_url: str
    thumb_url: str = ""
    width: int = 0
    height: int = 0
    review_id: str = Field(default="", max_length=32)


class AmazonCaptureImport(BaseModel):
    """Payload the extension posts after scraping one Amazon parent listing."""

    product_id: int
    account_key: str = ""
    parent_asin: str = Field(default="", max_length=32)
    price: float = 0.0
    title: str = ""
    source_brand: str = Field(default="", max_length=128)
    variations: list[AmazonVariationIn] = Field(default_factory=list)
    review_photos: list[AmazonReviewPhotoIn] = Field(default_factory=list)
    # reviewId -> colour, scraped from whatever review bodies the page rendered.
    review_colors: dict[str, str] = Field(default_factory=dict)


class DepopSourcePhotoRead(BaseModel):
    id: int
    product_id: int
    kind: str
    image_url: str
    thumb_url: str
    review_id: str = ""
    source_asin: str
    variant_label: str
    variant_id: int | None = None
    status: str
    width: int
    height: int
    sort_order: int
    crop_x: float = 0.0
    crop_y: float = 0.0
    crop_zoom: float = 1.0
    background_mode: str = "crop"
    model_config = ConfigDict(from_attributes=True)


class DepopPhotoQueueItem(BaseModel):
    product_id: int
    product_title: str
    variants: int
    pending: int
    approved: int
    rejected: int
    cover_image: str = ""


class DepopPhotoReviewRead(BaseModel):
    """Everything the swipe screen needs, in one request."""

    product_id: int
    product_title: str
    variants: list["DepopVariantRead"] = Field(default_factory=list)
    photos: list["DepopSourcePhotoRead"] = Field(default_factory=list)


class DepopPhotoDecision(BaseModel):
    status: str = Field(pattern=r"^(pending|approved|rejected)$")
    variant_id: int | None = None
    crop_x: float = Field(default=0.0, ge=-1.0, le=1.0)
    crop_y: float = Field(default=0.0, ge=-1.0, le=1.0)
    crop_zoom: float = Field(default=1.0, ge=1.0, le=4.0)
    background_mode: str = Field(default="crop", pattern=r"^(crop|blur)$")


class DepopImportResult(BaseModel):
    product_id: int
    variants_created: int
    variants_existing: int
    photos_created: int
    photos_skipped: int
    # Review photos auto-attributed to a variation via their review id.
    photos_matched: int = 0
    variants: list[DepopVariantRead] = Field(default_factory=list)
    photos: list[DepopSourcePhotoRead] = Field(default_factory=list)


class DepopJobCreate(BaseModel):
    variant_id: int
    action: str = Field(default="create", pattern=r"^(create|update|deactivate)$")
    scheduled_for: datetime | None = None


    @field_validator("scheduled_for")
    @classmethod
    def normalize_schedule_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class DepopJobUpdate(BaseModel):
    scheduled_for: datetime | None = None

    @field_validator("scheduled_for")
    @classmethod
    def normalize_schedule_utc(cls, value: datetime | None) -> datetime | None:
        return DepopJobCreate.normalize_schedule_utc(value)

    status: str | None = Field(default=None, pattern=r"^(queued|running|needs_review|completed|cancelled)$")
    progress: int | None = Field(default=None, ge=0, le=100)
    message: str | None = None
    runner_url: str | None = None


class DepopSubmissionBegin(BaseModel):
    account_key: str = Field(min_length=1, max_length=128)


class DepopPublicationConfirm(BaseModel):
    depop_listing_id: str = Field(min_length=1, max_length=128)
    listing_url: str = Field(default="", max_length=2048)
    published_at: datetime | None = None


class DepopJobRead(BaseModel):
    id: int
    variant_id: int
    account_key: str
    action: str
    status: str
    scheduled_for: datetime | None = None
    submission_started_at: datetime | None = None
    attempts: int
    progress: int
    message: str
    runner_url: str
    created_at: datetime
    updated_at: datetime
    # Embedded straight from the variant/product so depop-fill.js can fetch
    # everything it needs to fill a listing with a single GET, the same way
    # ListingJobRead embeds the eBay package.
    product_id: int | None = None
    sku: str = ""
    title: str = ""
    description: str = ""
    price: float | None = None
    image_urls: list[str] = Field(default_factory=list)
    local_image_paths: list[str] = Field(default_factory=list)
    size: str = ""
    brand: str = ""
    category: str = ""
    condition: str = ""
    color: str = ""
    shipping_method: str = ""
    shipping_weight_lb: float | None = None
    shipping_weight_source: str = ""
    depop_listing_id: str | None = None
    model_config = ConfigDict(from_attributes=True)


class DepopListingPackage(BaseModel):
    """What the depop-fill.js content script needs to fill one listing."""

    job_id: int
    variant_id: int
    product_id: int
    account_key: str
    sku: str
    title: str
    description: str = ""
    price: float
    image_urls: list[str] = Field(default_factory=list)
    local_image_paths: list[str] = Field(default_factory=list)
    size: str = ""
    brand: str = ""
    category: str = ""
    condition: str = ""
    color: str = ""
    shipping_method: str = ""
    shipping_weight_lb: float | None = None
    shipping_weight_source: str = ""


class DepopJobRunResult(BaseModel):
    job: DepopJobRead
    package: DepopListingPackage | None = None


class DepopApprovedBatchScheduleRequest(BaseModel):
    account_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,127}$")
    timezone: str = "America/Chicago"
    daily_hours: list[int] = Field(default_factory=lambda: list(range(0, 24, 2)), min_length=1, max_length=24)
    photos_per_listing: int = Field(default=4, ge=4, le=4)


class DepopApprovedBatchScheduleResult(BaseModel):
    jobs: list[DepopJobRead] = Field(default_factory=list)
    variants_created: int = 0
    listings_scheduled: int = 0
    approved_photos_used: int = 0
    approved_photos_remaining: int = 0

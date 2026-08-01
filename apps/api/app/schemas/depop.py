from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    price: float = Field(gt=0)
    image_ids: list[int] = Field(default_factory=list, max_length=4)
    size: str = ""
    brand: str = ""
    category: str = ""
    condition: str = ""
    color: str = ""


class DepopVariantUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None
    price: float | None = Field(default=None, gt=0)
    image_ids: list[int] | None = Field(default=None, max_length=4)
    size: str | None = None
    brand: str | None = None
    category: str | None = None
    condition: str | None = None
    color: str | None = None
    status: str | None = None


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
    status: str
    depop_listing_id: str | None = None
    published_at: datetime | None = None
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


class DepopImportResult(BaseModel):
    product_id: int
    variants_created: int
    variants_existing: int
    photos_created: int
    photos_skipped: int
    variants: list[DepopVariantRead] = Field(default_factory=list)
    photos: list[DepopSourcePhotoRead] = Field(default_factory=list)


class DepopJobCreate(BaseModel):
    variant_id: int
    action: str = Field(default="create", pattern=r"^(create|update|deactivate)$")
    scheduled_for: datetime | None = None


class DepopJobUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(queued|running|needs_review|completed|cancelled)$")
    progress: int | None = Field(default=None, ge=0, le=100)
    message: str | None = None
    runner_url: str | None = None


class DepopJobRead(BaseModel):
    id: int
    variant_id: int
    account_key: str
    action: str
    status: str
    scheduled_for: datetime | None = None
    attempts: int
    progress: int
    message: str
    runner_url: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

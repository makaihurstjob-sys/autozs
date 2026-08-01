from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.domain import TimestampMixin


class DepopAccount(Base, TimestampMixin):
    __tablename__ = "depop_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(128))
    username: Mapped[str] = mapped_column(String(128), default="")
    chrome_profile_root: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    writes_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class DepopListingVariant(Base, TimestampMixin):
    __tablename__ = "depop_listing_variants"
    __table_args__ = (UniqueConstraint("product_id", "variant_key", name="uq_depop_product_variant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    account_key: Mapped[str] = mapped_column(String(128), index=True)
    variant_key: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float)
    image_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    size: Mapped[str] = mapped_column(String(64), default="")
    brand: Mapped[str] = mapped_column(String(128), default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    condition: Mapped[str] = mapped_column(String(64), default="")
    color: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    depop_listing_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    jobs: Mapped[list["DepopListingJob"]] = relationship(back_populates="variant", cascade="all, delete-orphan")


class DepopSourcePhoto(Base, TimestampMixin):
    """A candidate photo pulled off an Amazon listing, awaiting swipe review.

    Two kinds land here. ``variation`` photos are the first gallery image for a
    child ASIN, so their ``variant_label`` is already known and trustworthy.
    ``review`` photos come from the customer-images carousel. They can often be
    attributed automatically by joining ``review_id`` to the review body that
    names a colour, but the product page renders only a handful of review
    bodies, so any photo whose review is not displayed arrives unassigned and is
    linked by hand during swipe review.

    While ``status`` is ``pending``, a populated ``variant_id`` is a *suggestion*
    the reviewer can accept or override; once approved it is the assignment.
    """

    __tablename__ = "depop_source_photos"
    __table_args__ = (UniqueConstraint("product_id", "image_url", name="uq_depop_source_photo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="review", index=True)
    image_url: Mapped[str] = mapped_column(Text)
    thumb_url: Mapped[str] = mapped_column(Text, default="")
    # The carousel's data-asin is the ASIN of whatever variation is being VIEWED,
    # not the one the reviewer bought -- the same photo reports a different asin
    # on each variation's page. data-reviewid is the only stable join key back to
    # the review body that names the colour.
    review_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    source_asin: Mapped[str] = mapped_column(String(32), default="")
    variant_label: Mapped[str] = mapped_column(String(128), default="")
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("depop_listing_variants.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class DepopListingJob(Base, TimestampMixin):
    __tablename__ = "depop_listing_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("depop_listing_variants.id"), index=True)
    account_key: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(32), default="create")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    runner_url: Mapped[str] = mapped_column(Text, default="")
    lease_owner: Mapped[str | None] = mapped_column(String(256), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    variant: Mapped[DepopListingVariant] = relationship(back_populates="jobs")

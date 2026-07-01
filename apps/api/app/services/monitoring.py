from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.domain import AutomationRun, Product, ProductStatus
from app.services.settings import read_pricing_settings
from app.services.importer import effective_supplier_cost


@dataclass(frozen=True)
class SourceRefreshItem:
    product_id: int
    sku: str
    title: str
    source_url: str | None
    source_price: float | None
    source_shipping: float
    draft_price: float | None
    estimated_profit: float | None
    image_count: int
    last_source_update: datetime | None
    age_days: int | None
    age_hours: float | None
    priority: str
    reason: str
    extension_ready: bool


@dataclass(frozen=True)
class SourceRefreshQueue:
    stale_after_days: int
    stale_after_hours: float
    total: int
    needs_refresh: int
    items: list[SourceRefreshItem]


@dataclass(frozen=True)
class SourceMonitoringResult:
    stale_after_days: int
    stale_after_hours: float
    total: int
    needs_refresh: int
    high_priority: int
    medium_priority: int
    extension_ready: int
    run_id: int
    message: str
    items: list[SourceRefreshItem]


def build_source_refresh_queue(db: Session, stale_after_days: int | None = None) -> SourceRefreshQueue:
    settings = read_pricing_settings(db)
    effective_stale_after_hours = (
        float(stale_after_days) * 24
        if stale_after_days is not None
        else float(settings.get("source_refresh_interval_hours", 6))
    )
    effective_stale_after_days = max(1, int(effective_stale_after_hours / 24))
    products = db.scalars(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.status != ProductStatus.deleted.value)
        .order_by(Product.created_at.desc())
    ).all()
    now = datetime.utcnow()
    items: list[SourceRefreshItem] = []
    for product in products:
        supplier = product.supplier_products[0] if product.supplier_products else None
        draft = product.listing_drafts[0] if product.listing_drafts else None
        source_price = supplier.last_price if supplier else None
        source_shipping = supplier.last_shipping if supplier else -1.0
        last_update = supplier.updated_at if supplier else None
        age_days = (now - last_update).days if last_update else None
        age_hours = round((now - last_update).total_seconds() / 3600, 1) if last_update else None
        estimated_profit = None
        if draft and draft.calculated_price is not None and source_price is not None:
            fee_rate = product.ebay_fee_rate + product.promoted_rate + product.return_risk_rate
            estimated_profit = round(draft.calculated_price - effective_supplier_cost(source_price, settings) - _shipping_cost(source_shipping) - (draft.calculated_price * fee_rate), 2)

        if supplier is None:
            priority = "high"
            reason = "No source URL attached"
        elif source_price is None:
            priority = "high"
            reason = "Missing source price"
        elif source_shipping is None or source_shipping < 0:
            priority = "high"
            reason = "Missing source shipping"
        elif age_hours is not None and age_hours >= effective_stale_after_hours:
            priority = "medium"
            reason = f"Source data is {age_hours:g} hour(s) old"
        elif estimated_profit is not None and estimated_profit < float(settings["default_min_profit"]):
            priority = "medium"
            reason = f"Profit {estimated_profit:.2f} is below minimum {float(settings['default_min_profit']):.2f}"
        else:
            priority = "low"
            reason = "Fresh enough"

        items.append(
            SourceRefreshItem(
                product_id=product.id,
                sku=product.sku,
                title=product.title,
                source_url=supplier.source_url if supplier else None,
                source_price=source_price,
                source_shipping=source_shipping,
                draft_price=draft.calculated_price if draft else None,
                estimated_profit=estimated_profit,
                image_count=len(product.images),
                last_source_update=last_update,
                age_days=age_days,
                age_hours=age_hours,
                priority=priority,
                reason=reason,
                extension_ready=bool(supplier and supplier.source_url),
            )
        )
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda item: (priority_order[item.priority], -(item.age_days or 0), item.title))
    return SourceRefreshQueue(
        stale_after_days=effective_stale_after_days,
        stale_after_hours=effective_stale_after_hours,
        total=len(items),
        needs_refresh=sum(1 for item in items if item.priority in {"high", "medium"}),
        items=items,
    )


def run_source_monitoring_cycle(db: Session, stale_after_days: int | None = None) -> SourceMonitoringResult:
    queue = build_source_refresh_queue(db, stale_after_days=stale_after_days)
    high_priority = sum(1 for item in queue.items if item.priority == "high")
    medium_priority = sum(1 for item in queue.items if item.priority == "medium")
    extension_ready = sum(1 for item in queue.items if item.priority in {"high", "medium"} and item.extension_ready)
    message = (
        f"Source monitoring found {queue.needs_refresh} product(s) needing refresh "
        f"({high_priority} high, {medium_priority} medium); {extension_ready} can be refreshed with browser capture."
    )
    run = AutomationRun(task_name="source_monitoring", status="completed", message=message)
    db.add(run)
    db.commit()
    db.refresh(run)
    return SourceMonitoringResult(
        stale_after_days=queue.stale_after_days,
        stale_after_hours=queue.stale_after_hours,
        total=queue.total,
        needs_refresh=queue.needs_refresh,
        high_priority=high_priority,
        medium_priority=medium_priority,
        extension_ready=extension_ready,
        run_id=run.id,
        message=message,
        items=queue.items,
    )


def _shipping_cost(value: float | None) -> float:
    if value is None or value < 0:
        return 0.0
    return float(value)

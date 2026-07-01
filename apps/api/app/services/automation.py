from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.domain import AutomationRun, PriceSnapshot, Product, ProductStatus, SnapshotSource
from app.services.importer import download_missing_product_images, recalculate_all_draft_prices
from app.services.repricing import decide_reprice
from app.services.settings import read_pricing_settings


@dataclass(frozen=True)
class CatalogAutomationResult:
    draft_prices_updated: int
    repricing_snapshots: int
    image_products_checked: int
    image_products_attempted: int
    image_download_attempted: int
    image_downloaded: int


def create_repricing_snapshots(db: Session, product_ids: list[int] | None = None) -> list[PriceSnapshot]:
    settings = read_pricing_settings(db)
    gift_card_discount = (
        float(settings.get("default_gift_card_discount_percent", 0.0))
        if bool(settings.get("default_gift_card_discount_enabled", False))
        else 0.0
    )
    statement = (
        select(Product)
        .options(selectinload(Product.supplier_products))
        .where(Product.status != ProductStatus.deleted.value)
    )
    if product_ids is not None:
        statement = statement.where(Product.id.in_(product_ids))
    products = db.scalars(statement).all()
    snapshots: list[PriceSnapshot] = []
    for product in products:
        supplier = product.supplier_products[0] if product.supplier_products else None
        decision = decide_reprice(product, supplier, gift_card_discount)
        snapshot = PriceSnapshot(
            product_id=product.id,
            source=SnapshotSource.calculated.value,
            price=supplier.last_price if supplier else None,
            shipping=supplier.last_shipping if supplier else -1.0,
            floor_price=decision.floor_price,
            suggested_price=decision.suggested_price,
            message=decision.message,
        )
        db.add(snapshot)
        snapshots.append(snapshot)
    db.commit()
    for snapshot in snapshots:
        db.refresh(snapshot)
    return snapshots


def run_catalog_automation_cycle(db: Session) -> CatalogAutomationResult:
    products = recalculate_all_draft_prices(db)
    draft_prices_updated = sum(
        1
        for product in products
        if product.listing_drafts and product.listing_drafts[0].calculated_price is not None
    )
    repricing_snapshots = len(create_repricing_snapshots(db))
    checked, attempted_products, attempted, downloaded, _ = download_missing_product_images(db)
    result = CatalogAutomationResult(
        draft_prices_updated=draft_prices_updated,
        repricing_snapshots=repricing_snapshots,
        image_products_checked=checked,
        image_products_attempted=attempted_products,
        image_download_attempted=attempted,
        image_downloaded=downloaded,
    )
    db.add(
        AutomationRun(
            task_name="catalog_cycle",
            status="completed",
            draft_prices_updated=result.draft_prices_updated,
            repricing_snapshots=result.repricing_snapshots,
            image_products_checked=result.image_products_checked,
            image_products_attempted=result.image_products_attempted,
            image_download_attempted=result.image_download_attempted,
            image_downloaded=result.image_downloaded,
            message="Catalog cycle completed",
        )
    )
    db.commit()
    return result

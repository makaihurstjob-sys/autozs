import html
import base64
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha1
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, unquote, urlparse, urlunparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import PROJECT_ROOT
from app.models.domain import EbayListing, ListingDraft, PriceSnapshot, Product, ProductImage, ProductStatus, SnapshotSource, SupplierProduct
from app.services.settings import read_pricing_settings


@dataclass(frozen=True)
class ImportedProductData:
    source_url: str
    supplier: str
    supplier_sku: str | None
    title: str
    source_price: float | None
    description: str
    image_urls: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ListingPriceDecision:
    final_price: float | None
    margin_price: float | None
    competitor_target_price: float | None
    minimum_profit_price: float | None
    safe_competitor_price: float | None
    strategy: str
    reason: str


def split_urls(urls: str) -> list[str]:
    lines = [line.strip() for line in urls.splitlines() if line.strip()]
    if len(lines) == 1 and "," in lines[0] and not lines[0].startswith("data:image/"):
        return [part.strip() for part in lines[0].split(",") if part.strip()]
    return lines


INTERNAL_SOURCE_QUERY_PARAMS = {"ea_auto_import", "auto_download_test"}


def normalize_source_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return url.strip()
    if not parsed.query:
        return url.strip()
    query = urlencode(
        [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in INTERNAL_SOURCE_QUERY_PARAMS],
        doseq=True,
    )
    return urlunparse(parsed._replace(query=query))


NOISY_DESCRIPTION_PATTERNS = re.compile(
    r"sponsored|advertisement|sign in|view more details|customer service|check order status|"
    r"pickup,\s*shipping|pay your credit card|order cancellation|privacy|terms of use|"
    r"download our app|special financing|subscribe|local store prices",
    re.I,
)

NOISY_IMAGE_PATTERNS = re.compile(
    r"contentgrid|heroflattenimage|rackcdn|dropdown|disinfecting-wipes|"
    r"memorial-day|christmasdelivery|decorative-header",
    re.I,
)


def calculate_markup_price(source_price: float, fee_rate: float, margin_percent: float) -> float:
    factor = 1 - fee_rate
    if factor <= 0:
        raise ValueError("Fee rate must leave room for a selling price")
    return round((source_price * (1 + margin_percent)) / factor, 2)


def calculate_minimum_profit_price(landed_cost: float | None, fee_rate: float, minimum_profit: float) -> float | None:
    if landed_cost is None:
        return None
    factor = 1 - fee_rate
    if factor <= 0:
        raise ValueError("Fee rate must leave room for a selling price")
    return round((landed_cost + minimum_profit) / factor, 2)


def calculate_listing_price(
    source_price: float | None,
    competitor_price: float | None,
    settings: dict[str, float | bool | str],
) -> ListingPriceDecision:
    margin_price = (
        calculate_markup_price(
            source_price,
            _fee_rate_total(settings),
            float(settings["default_margin_percent"]),
        )
        if source_price is not None
        else None
    )
    competitor_target = (
        round(competitor_price - float(settings["default_undercut_amount"]), 2)
        if competitor_price is not None
        else None
    )
    minimum_profit_price = calculate_minimum_profit_price(
        source_price,
        _fee_rate_total(settings),
        float(settings["default_min_profit"]),
    )
    safe_competitor_price = _max_optional(competitor_target, minimum_profit_price)
    strategy = str(settings.get("default_pricing_strategy", "margin"))
    if strategy == "competitor" and competitor_target is not None:
        final_price = competitor_target
        reason = "Competitor pricing: competitor minus configured undercut"
    elif strategy == "safe_competitor" and safe_competitor_price is not None:
        final_price = safe_competitor_price
        reason = "Safe competitor pricing: competitor undercut protected by minimum profit floor"
    else:
        final_price = margin_price
        reason = "Margin pricing: source cost plus configured margin and total fee assumptions"
    if (
        final_price is not None
        and minimum_profit_price is not None
        and bool(settings.get("default_min_profit_guard_enabled", False))
        and final_price < minimum_profit_price
    ):
        final_price = minimum_profit_price
        reason = f"{reason}; raised to the minimum-profit guard"
    if final_price is not None and bool(settings.get("default_round_to_99", False)):
        cents = _rounding_cents(settings)
        final_price = _round_up_to_cents(final_price, cents)
        reason = f"{reason}; rounded up to {cents:.2f}"
    return ListingPriceDecision(final_price, margin_price, competitor_target, minimum_profit_price, safe_competitor_price, strategy, reason)


def calculate_profit(sell_price: float | None, source_price: float | None, source_shipping: float, settings: dict[str, float | bool | str]) -> dict:
    if sell_price is None or source_price is None:
        return {"fees": None, "profit": None}
    fee_rate = _fee_rate_total(settings)
    fees = round(sell_price * fee_rate, 2)
    profit = round(sell_price - effective_supplier_cost(source_price, settings) - _shipping_cost(source_shipping) - fees, 2)
    return {"fees": fees, "profit": profit}


def effective_supplier_cost(source_price: float, settings: dict[str, float | bool | str]) -> float:
    if not bool(settings.get("default_gift_card_discount_enabled", False)):
        return float(source_price)
    discount = max(0.0, min(float(settings.get("default_gift_card_discount_percent", 0.0)), 100.0))
    return round(float(source_price) * (1 - discount / 100), 2)


def effective_landed_cost(source_price: float | None, source_shipping: float | None, settings: dict[str, float | bool | str]) -> float | None:
    if source_price is None:
        return None
    return effective_supplier_cost(source_price, settings) + _shipping_cost(source_shipping)


def _max_optional(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def choose_product_draft_price(db: Session, product_id: int, mode: str) -> Product | None:
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id == product_id)
    )
    if product is None:
        return None
    settings = read_pricing_settings(db)
    supplier = product.supplier_products[0] if product.supplier_products else None
    source_price = supplier.last_price if supplier else None
    source_shipping = supplier.last_shipping if supplier else -1.0
    landed_cost = effective_landed_cost(source_price, source_shipping, settings)
    price_decision = calculate_listing_price(landed_cost, product.competitor_price, settings)
    if mode == "margin":
        selected_price = price_decision.margin_price
        message = "Manual override: margin-safe draft price selected"
    elif mode == "competitor":
        selected_price = price_decision.competitor_target_price
        message = "Manual override: competitor draft price selected"
    elif mode == "safe_competitor":
        selected_price = price_decision.safe_competitor_price
        message = "Manual override: safe competitor price selected"
    else:
        selected_price = price_decision.minimum_profit_price
        message = "Manual override: minimum-profit draft price selected"
    if (
        selected_price is not None
        and price_decision.minimum_profit_price is not None
        and bool(settings.get("default_min_profit_guard_enabled", False))
        and selected_price < price_decision.minimum_profit_price
    ):
        selected_price = price_decision.minimum_profit_price
        message = f"{message}; raised to the minimum-profit guard"
    if selected_price is not None and bool(settings.get("default_round_to_99", False)):
        cents = _rounding_cents(settings)
        selected_price = _round_up_to_cents(selected_price, cents)
        message = f"{message}; rounded up to {cents:.2f}"

    draft = product.listing_drafts[0] if product.listing_drafts else None
    if draft is None:
        draft = ListingDraft(
            product_id=product.id,
            title=_listing_title(product.title, settings, _infer_brand(product.title)),
            description=_description_from_capture(product.title, None, settings),
        )
        db.add(draft)
    draft.calculated_price = selected_price
    draft.source_price = source_price
    draft.margin_percent = float(settings["default_margin_percent"])
    draft.ebay_fee_rate = float(settings["default_ebay_fee_rate"])

    if selected_price is not None:
        db.add(
            PriceSnapshot(
                product_id=product.id,
                source=SnapshotSource.calculated.value,
                price=source_price,
                shipping=source_shipping,
                floor_price=price_decision.margin_price,
                suggested_price=selected_price,
                message=message,
            )
        )
    db.commit()
    return db.scalar(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id == product_id)
    )


def recalculate_all_draft_prices(db: Session, product_ids: list[int] | None = None) -> list[Product]:
    settings = read_pricing_settings(db)
    statement = (
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.status != ProductStatus.deleted.value)
    )
    if product_ids is not None:
        statement = statement.where(Product.id.in_(product_ids))
    products = db.scalars(statement).all()
    updated_ids: list[int] = []
    for product in products:
        product.desired_profit = float(settings["default_min_profit"])
        product.risk_buffer = float(settings["default_risk_buffer"])
        product.ebay_fee_rate = float(settings["default_ebay_fee_rate"])
        product.promoted_rate = float(settings["default_promoted_rate"])
        product.return_risk_rate = float(settings["default_return_risk_rate"])
        product.undercut_amount = float(settings["default_undercut_amount"])
        supplier = product.supplier_products[0] if product.supplier_products else None
        source_price = supplier.last_price if supplier else None
        source_shipping = supplier.last_shipping if supplier else -1.0
        landed_cost = effective_landed_cost(source_price, source_shipping, settings)
        price_decision = calculate_listing_price(landed_cost, product.competitor_price, settings)
        draft = product.listing_drafts[0] if product.listing_drafts else None
        if draft is None:
            draft = ListingDraft(
                product_id=product.id,
                title=_listing_title(product.title, settings, _infer_brand(product.title)),
                description=_description_from_capture(product.title, None, settings),
            )
            db.add(draft)
        draft.title = draft.title or _listing_title(product.title, settings, _infer_brand(product.title))
        draft.description = draft.description or _description_from_capture(product.title, None, settings)
        draft.source_price = source_price
        draft.calculated_price = price_decision.final_price
        draft.margin_percent = float(settings["default_margin_percent"])
        draft.ebay_fee_rate = float(settings["default_ebay_fee_rate"])
        if price_decision.final_price is not None:
            db.add(
                PriceSnapshot(
                    product_id=product.id,
                    source=SnapshotSource.calculated.value,
                    price=source_price,
                    shipping=source_shipping,
                    floor_price=price_decision.margin_price,
                    suggested_price=price_decision.final_price,
                    message=f"Draft recalculated: {price_decision.reason}",
                )
            )
        updated_ids.append(product.id)
    db.commit()
    if not updated_ids:
        return []
    return list(
        db.scalars(
            select(Product)
            .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
            .where(Product.id.in_(updated_ids))
        ).all()
    )


def extract_product_data(source_url: str, source_price_override: float | None = None) -> ImportedProductData:
    source_url = normalize_source_url(source_url)
    warnings: list[str] = []
    html_text = ""
    try:
        response = httpx.get(
            source_url,
            follow_redirects=True,
            timeout=20,
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            },
        )
        if response.status_code == 200:
            html_text = response.text
        else:
            if response.status_code == 403 and "homedepot.com" in source_url:
                warnings.append(
                    "Home Depot blocked server-side price capture; use browser capture or fill source price in Products"
                )
            else:
                warnings.append(f"Source returned HTTP {response.status_code}; used URL fallback fields")
    except httpx.HTTPError as exc:
        warnings.append(f"Source fetch failed: {exc}; used URL fallback fields")

    structured = _extract_json_ld(html_text)
    title = _first_text(
        structured.get("name"),
        _meta(html_text, "og:title"),
        _title_from_url(source_url),
    )
    supplier_sku = _sku_from_url(source_url)
    source_price = source_price_override or _price_from_structured(structured) or _price_from_text(html_text)
    description = _generate_description(title, structured, html_text)
    images = _dedupe(
        [
            *_images_from_structured(structured),
            *_images_from_html(html_text),
            _meta(html_text, "og:image"),
        ]
    )
    if not images and "homedepot.com" in source_url:
        images = [_homedepot_image_guess(source_url)]
        warnings.append("Image URL was inferred from the Home Depot product id")
    if source_price is None:
        warnings.append("No source price captured; margin and draft price need source price before listing")

    return ImportedProductData(
        source_url=source_url,
        supplier="home_depot" if "homedepot.com" in source_url else "source_site",
        supplier_sku=supplier_sku,
        title=title[:512],
        source_price=source_price,
        description=description,
        image_urls=images,
        warnings=warnings,
    )


def import_products(
    db: Session,
    urls: list[str],
    supplier_override: str | None = None,
    source_price_override: float | None = None,
    source_shipping_override: float | None = None,
    competitor_price: float | None = None,
) -> tuple[list[Product], list[str]]:
    settings = read_pricing_settings(db)
    products: list[Product] = []
    warnings: list[str] = []
    for url in urls:
        url = normalize_source_url(url)
        data = extract_product_data(url, source_price_override)
        if supplier_override:
            data = ImportedProductData(
                source_url=data.source_url,
                supplier=supplier_override,
                supplier_sku=data.supplier_sku,
                title=data.title,
                source_price=data.source_price,
                description=data.description,
                image_urls=data.image_urls,
                warnings=data.warnings,
            )
        data_warnings = list(data.warnings)
        blocked_keyword = _matching_blacklist_keyword(data.title, settings)
        if blocked_keyword:
            warnings.append(f"{data.title}: blocked by keyword blacklist ({blocked_keyword})")
            continue
        external_key = sha1(data.source_url.encode()).hexdigest()[:10]
        sku = f"SRC-{external_key.upper()}"
        product = _find_product_for_source(db, data.source_url, sku)
        if product is None:
            product = Product(
                sku=sku,
                title=data.title,
                status=ProductStatus.monitoring.value,
                competitor_price=competitor_price,
                desired_profit=float(settings["default_min_profit"]),
                risk_buffer=float(settings["default_risk_buffer"]),
                ebay_fee_rate=float(settings["default_ebay_fee_rate"]),
                promoted_rate=float(settings["default_promoted_rate"]),
                return_risk_rate=float(settings["default_return_risk_rate"]),
                undercut_amount=float(settings["default_undercut_amount"]),
            )
            db.add(product)
            db.flush()
        else:
            product.title = data.title
            product.status = ProductStatus.monitoring.value
            if competitor_price is not None:
                product.competitor_price = competitor_price
        _archive_source_duplicates(db, product, data.source_url)

        supplier = db.scalar(select(SupplierProduct).where(SupplierProduct.product_id == product.id))
        if supplier is None:
            supplier = SupplierProduct(product_id=product.id, supplier=data.supplier, source_url=data.source_url)
            supplier.last_shipping = -1.0
            db.add(supplier)
        supplier.source_url = data.source_url
        supplier.supplier_sku = data.supplier_sku
        if data.source_price is not None:
            supplier.last_price = data.source_price
        if source_shipping_override is not None:
            supplier.last_shipping = source_shipping_override
        supplier.in_stock = True

        existing_image_count = db.scalar(select(ProductImage).where(ProductImage.product_id == product.id).limit(1)) is not None
        used_inferred_image = any("Image URL was inferred" in warning for warning in data_warnings)
        if data.image_urls and not (used_inferred_image and existing_image_count):
            _sync_product_images(db, product.id, data.image_urls)
        elif used_inferred_image and existing_image_count:
            data_warnings = [warning for warning in data_warnings if "Image URL was inferred" not in warning]

        effective_source_price = data.source_price if data.source_price is not None else supplier.last_price
        if effective_source_price is not None:
            data_warnings = [warning for warning in data_warnings if "No source price captured" not in warning]
        _log_supplier_snapshot(
            db,
            product.id,
            effective_source_price,
            supplier.last_shipping,
            "Supplier import refreshed from source URL",
        )
        landed_cost = effective_landed_cost(effective_source_price, supplier.last_shipping, settings)
        price_decision = calculate_listing_price(landed_cost, product.competitor_price, settings)
        draft = db.scalar(select(ListingDraft).where(ListingDraft.product_id == product.id))
        if draft is None:
            draft = ListingDraft(
                product_id=product.id,
                title=data.title,
                description=_description_from_capture(data.title, data.description, settings),
            )
            db.add(draft)
        draft.title = _listing_title(data.title, settings, _infer_brand(data.title))
        if _should_replace_listing_description(draft.description, data.description, data_warnings):
            draft.description = _description_from_capture(data.title, data.description, settings)
        draft.source_price = effective_source_price
        draft.calculated_price = price_decision.final_price
        draft.margin_percent = float(settings["default_margin_percent"])
        draft.ebay_fee_rate = float(settings["default_ebay_fee_rate"])

        if price_decision.final_price is not None:
            db.add(
                PriceSnapshot(
                    product_id=product.id,
                    source=SnapshotSource.calculated.value,
                    price=effective_source_price,
                    shipping=supplier.last_shipping,
                    floor_price=price_decision.margin_price,
                    suggested_price=price_decision.final_price,
                    message=price_decision.reason,
                )
            )
        warnings.extend([f"{data.title}: {warning}" for warning in data_warnings])
        products.append(product)

    db.commit()
    ids = [product.id for product in products]
    refreshed = db.scalars(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id.in_(ids))
    ).all()
    return list(refreshed), warnings


def import_captured_product(
    db: Session,
    source_url: str,
    title: str,
    source_price: float | None = None,
    source_shipping: float | None = None,
    competitor_price: float | None = None,
    subscription_discount_percent: float | None = None,
    description: str | None = None,
    image_urls: str | None = None,
) -> Product:
    source_url = normalize_source_url(source_url)
    settings = read_pricing_settings(db)
    external_key = sha1(source_url.encode()).hexdigest()[:10]
    sku = f"SRC-{external_key.upper()}"
    product = _find_product_for_source(db, source_url, sku)
    if product is None:
        product = Product(
            sku=sku,
            title=title[:512],
            status=ProductStatus.monitoring.value,
            competitor_price=competitor_price,
            desired_profit=float(settings["default_min_profit"]),
            risk_buffer=float(settings["default_risk_buffer"]),
            ebay_fee_rate=float(settings["default_ebay_fee_rate"]),
            promoted_rate=float(settings["default_promoted_rate"]),
            return_risk_rate=float(settings["default_return_risk_rate"]),
            undercut_amount=float(settings["default_undercut_amount"]),
        )
        db.add(product)
        db.flush()
    else:
        product.title = title[:512]
        product.status = ProductStatus.monitoring.value
        if competitor_price is not None:
            product.competitor_price = competitor_price
    _archive_source_duplicates(db, product, source_url)

    supplier = db.scalar(select(SupplierProduct).where(SupplierProduct.product_id == product.id))
    if supplier is None:
        supplier = SupplierProduct(
            product_id=product.id,
            supplier="home_depot" if "homedepot.com" in source_url else "source_site",
            source_url=source_url,
            last_shipping=-1.0,
        )
        db.add(supplier)
    supplier.source_url = source_url
    supplier.supplier_sku = _sku_from_url(source_url)
    if source_price is not None:
        supplier.last_price = source_price
    if source_shipping is not None:
        supplier.last_shipping = source_shipping
    if subscription_discount_percent is not None:
        supplier.subscription_discount_percent = subscription_discount_percent
    supplier.in_stock = True
    supplier.updated_at = datetime.utcnow()
    effective_source_price = source_price if source_price is not None else supplier.last_price
    _log_supplier_snapshot(
        db,
        product.id,
        effective_source_price,
        supplier.last_shipping,
        "Supplier browser capture refreshed",
    )
    landed_cost = effective_landed_cost(effective_source_price, supplier.last_shipping, settings)

    if image_urls is not None:
        _sync_product_images(db, product.id, _filter_source_images(source_url, split_urls(image_urls)))

    draft = db.scalar(select(ListingDraft).where(ListingDraft.product_id == product.id))
    if draft is None:
        draft = ListingDraft(product_id=product.id, title=_listing_title(title, settings, _infer_brand(title)), description="")
        db.add(draft)
    price_decision = calculate_listing_price(landed_cost, product.competitor_price, settings)
    draft.title = _listing_title(title, settings, _infer_brand(title))
    draft.description = _description_from_capture(title, description, settings)
    draft.source_price = effective_source_price
    draft.calculated_price = price_decision.final_price
    draft.margin_percent = float(settings["default_margin_percent"])
    draft.ebay_fee_rate = float(settings["default_ebay_fee_rate"])

    if price_decision.final_price is not None:
        db.add(
            PriceSnapshot(
                product_id=product.id,
                source=SnapshotSource.calculated.value,
                price=effective_source_price,
                shipping=supplier.last_shipping,
                floor_price=price_decision.margin_price,
                suggested_price=price_decision.final_price,
                message=price_decision.reason,
            )
        )
    db.commit()
    return db.scalar(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id == product.id)
    )


def update_product_from_capture(
    db: Session,
    product_id: int,
    title: str | None = None,
    source_price: float | None = None,
    source_shipping: float | None = None,
    competitor_price: float | None = None,
    subscription_discount_percent: float | None = None,
    description: str | None = None,
    image_urls: str | None = None,
) -> Product | None:
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id == product_id)
    )
    if product is None:
        return None
    settings = read_pricing_settings(db)
    if title:
        product.title = title[:512]
    if competitor_price is not None:
        product.competitor_price = competitor_price

    supplier = product.supplier_products[0] if product.supplier_products else None
    if supplier and source_price is not None:
        supplier.last_price = source_price
    if supplier and source_shipping is not None:
        supplier.last_shipping = source_shipping
    if supplier and subscription_discount_percent is not None:
        supplier.subscription_discount_percent = subscription_discount_percent
    if supplier:
        supplier.updated_at = datetime.utcnow()
    effective_source_price = source_price if source_price is not None else (supplier.last_price if supplier else None)
    effective_source_shipping = source_shipping if source_shipping is not None else (supplier.last_shipping if supplier else -1.0)
    if supplier:
        _log_supplier_snapshot(
            db,
            product.id,
            effective_source_price,
            effective_source_shipping,
            "Supplier capture update refreshed",
        )
    landed_cost = effective_landed_cost(effective_source_price, effective_source_shipping, settings)

    if image_urls is not None:
        source_url = supplier.source_url if supplier else ""
        _sync_product_images(db, product.id, _filter_source_images(source_url, split_urls(image_urls)))

    draft = product.listing_drafts[0] if product.listing_drafts else None
    if draft is None:
        draft = ListingDraft(product_id=product.id, title=_listing_title(product.title, settings, _infer_brand(product.title)), description="")
        db.add(draft)
    if title:
        draft.title = _listing_title(title, settings, _infer_brand(title))
    if description is not None:
        draft.description = _description_from_capture(title or product.title, description, settings)
    draft.source_price = effective_source_price
    draft.margin_percent = float(settings["default_margin_percent"])
    draft.ebay_fee_rate = float(settings["default_ebay_fee_rate"])
    price_decision = calculate_listing_price(landed_cost, product.competitor_price, settings)
    draft.calculated_price = price_decision.final_price

    if draft.calculated_price is not None:
        db.add(
            PriceSnapshot(
                product_id=product.id,
                source=SnapshotSource.calculated.value,
                price=effective_source_price,
                shipping=effective_source_shipping,
                floor_price=price_decision.margin_price,
                suggested_price=draft.calculated_price,
                message=price_decision.reason,
            )
        )

    db.commit()
    return db.scalar(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id == product_id)
    )


def download_product_images(db: Session, product_id: int) -> tuple[int, int, list[ProductImage]] | None:
    product = db.scalar(select(Product).options(selectinload(Product.images)).where(Product.id == product_id))
    if product is None:
        return None
    attempted = 0
    downloaded = 0
    for image in product.images:
        attempted += 1
        image.local_path = _download_image(product_id, image.image_url, image.sort_order)
        if image.local_path:
            downloaded += 1
    db.commit()
    return attempted, downloaded, list(product.images)


def download_missing_product_images(db: Session) -> tuple[int, int, int, int, list[tuple[int, int, int, list[ProductImage]]]]:
    products = db.scalars(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.status != ProductStatus.deleted.value)
        .order_by(Product.created_at.desc())
    ).all()
    checked = len(products)
    attempted_products = 0
    attempted = 0
    downloaded = 0
    results: list[tuple[int, int, int, list[ProductImage]]] = []
    for product in products:
        missing_images = [image for image in product.images if not image.local_path]
        if not missing_images:
            continue
        attempted_products += 1
        product_attempted = 0
        product_downloaded = 0
        for image in missing_images:
            product_attempted += 1
            attempted += 1
            image.local_path = _download_image(product.id, image.image_url, image.sort_order)
            if image.local_path:
                product_downloaded += 1
                downloaded += 1
        results.append((product.id, product_attempted, product_downloaded, list(product.images)))
    db.commit()
    return checked, attempted_products, attempted, downloaded, results


def _find_product_for_source(db: Session, source_url: str, sku: str) -> Product | None:
    normalized_source_url = normalize_source_url(source_url)
    candidate_ids: set[int] = set()
    sku_product_id = db.scalar(select(Product.id).where(Product.sku == sku))
    if sku_product_id is not None:
        candidate_ids.add(sku_product_id)

    for supplier in db.scalars(select(SupplierProduct)).all():
        if normalize_source_url(supplier.source_url) == normalized_source_url:
            candidate_ids.add(supplier.product_id)

    if not candidate_ids:
        return None

    products = list(
        db.scalars(
            select(Product)
            .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
            .where(Product.id.in_(candidate_ids))
        ).all()
    )
    if not products:
        return None
    return max(products, key=_product_source_match_score)


def _product_source_match_score(product: Product) -> tuple[int, int, int, int, int, int]:
    supplier = product.supplier_products[0] if product.supplier_products else None
    draft = product.listing_drafts[0] if product.listing_drafts else None
    local_images = sum(1 for image in product.images if image.local_path)
    downloaded_or_captured_images = len(product.images)
    has_source_price = int(bool(supplier and supplier.last_price is not None))
    has_source_shipping = int(bool(supplier and supplier.last_shipping is not None and supplier.last_shipping >= 0))
    has_listing_description = int(bool(draft and draft.description and "Product details are summarized from the source listing" not in draft.description))
    active_status = int(product.status != ProductStatus.deleted.value)
    return (
        active_status,
        local_images,
        downloaded_or_captured_images,
        has_listing_description,
        has_source_price,
        has_source_shipping,
    )


def _archive_source_duplicates(db: Session, canonical_product: Product, source_url: str) -> None:
    normalized_source_url = normalize_source_url(source_url)
    duplicate_ids = {
        supplier.product_id
        for supplier in db.scalars(select(SupplierProduct)).all()
        if supplier.product_id != canonical_product.id and normalize_source_url(supplier.source_url) == normalized_source_url
    }
    for product_id in duplicate_ids:
        has_listing = db.scalar(select(EbayListing.id).where(EbayListing.product_id == product_id).limit(1)) is not None
        if has_listing:
            continue
        duplicate = db.get(Product, product_id)
        if duplicate is not None:
            duplicate.status = ProductStatus.deleted.value


def _sync_product_images(db: Session, product_id: int, image_urls: list[str]) -> None:
    incoming = _dedupe([url.strip() for url in image_urls if url.strip()])
    existing_images = db.scalars(select(ProductImage).where(ProductImage.product_id == product_id)).all()
    existing_by_url = {image.image_url: image for image in existing_images}
    incoming_set = set(incoming)

    for image in existing_images:
        if image.image_url not in incoming_set:
            db.delete(image)

    for index, image_url in enumerate(incoming):
        existing_image = existing_by_url.get(image_url)
        if existing_image is None:
            db.add(
                ProductImage(
                    product_id=product_id,
                    image_url=image_url,
                    local_path=_download_image(product_id, image_url, index),
                    sort_order=index,
                )
            )
        else:
            existing_image.sort_order = index
            if existing_image.local_path is None:
                existing_image.local_path = _download_image(product_id, image_url, index)


def _log_supplier_snapshot(db: Session, product_id: int, price: float | None, shipping: float | None, message: str) -> None:
    if price is None and shipping is None:
        return
    db.add(
        PriceSnapshot(
            product_id=product_id,
            source=SnapshotSource.supplier.value,
            price=price,
            shipping=shipping if shipping is not None else -1.0,
            message=message,
        )
    )


def _filter_source_images(source_url: str, image_urls: list[str]) -> list[str]:
    incoming = _dedupe([url.strip() for url in image_urls if url.strip()])
    if "homedepot.com" not in source_url:
        return incoming
    product_images = [
        url
        for url in incoming
        if "images.thdstatic.com/productImages/" in url and not NOISY_IMAGE_PATTERNS.search(url)
    ]
    return product_images or [url for url in incoming if not NOISY_IMAGE_PATTERNS.search(url)]


def build_ebay_listing_package(db: Session, product_id: int, listing_schedule_at: str | None = None) -> dict | None:
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.supplier_products), selectinload(Product.images), selectinload(Product.listing_drafts))
        .where(Product.id == product_id)
    )
    if product is None:
        return None
    supplier = product.supplier_products[0] if product.supplier_products else None
    draft = product.listing_drafts[0] if product.listing_drafts else None
    settings = read_pricing_settings(db)
    source_price = supplier.last_price if supplier else None
    source_shipping = supplier.last_shipping if supplier else -1.0
    landed_cost = effective_landed_cost(source_price, source_shipping, settings)
    price_decision = calculate_listing_price(
        landed_cost,
        product.competitor_price,
        settings,
    )
    active_profit = calculate_profit(draft.calculated_price if draft else None, source_price, source_shipping, settings)
    margin_profit = calculate_profit(price_decision.margin_price, source_price, source_shipping, settings)
    competitor_profit = calculate_profit(price_decision.competitor_target_price, source_price, source_shipping, settings)
    minimum_profit_target_profit = calculate_profit(price_decision.minimum_profit_price, source_price, source_shipping, settings)
    safe_competitor_profit = calculate_profit(price_decision.safe_competitor_price, source_price, source_shipping, settings)
    minimum_profit = float(settings["default_min_profit"])
    profit_gap = (
        round(minimum_profit - active_profit["profit"], 2)
        if active_profit["profit"] is not None
        else None
    )
    warnings = _listing_profit_warnings(active_profit["profit"], minimum_profit, price_decision)
    offers_enabled = bool(settings.get("default_offers_enabled", False))
    listing_schedule_mode = "scheduled" if listing_schedule_at else str(settings.get("default_listing_schedule_mode", "now"))
    listing_schedule_at = listing_schedule_at or _default_listing_schedule_at(settings)
    item_specifics = listing_item_specifics(product, supplier)
    title = _listing_title(draft.title if draft else product.title, settings, item_specifics.get("Brand"))
    description = _apply_description_template(
        title,
        draft.description if draft else _description_from_capture(product.title, None, settings),
        settings,
    )
    shipping_cost_type = str(settings.get("default_shipping_cost_type", "flat"))
    domestic_shipping_service = str(settings.get("default_domestic_shipping_service", "Economy Shipping"))
    buyer_shipping_cost = float(settings.get("default_buyer_shipping_cost", 0.0))
    item_condition = str(settings.get("default_item_condition", "New")).strip() or "New"
    sorted_images = sorted(product.images, key=lambda img: img.sort_order)
    clean_image_urls = _filter_source_images(
        supplier.source_url if supplier else "",
        [image.image_url for image in sorted_images],
    )
    clean_image_url_set = set(clean_image_urls)
    local_image_paths = [image.local_path for image in sorted_images if image.local_path and image.image_url in clean_image_url_set]
    manual_image_paths = _uploadable_local_image_paths(local_image_paths)
    missing_image_count = max(len(clean_image_urls) - len(local_image_paths), 0)
    image_upload_status = (
        "ready"
        if clean_image_urls and missing_image_count == 0 and manual_image_paths
        else "missing_downloads"
        if clean_image_urls
        else "missing_images"
    )
    return {
        "product_id": product.id,
        "sku": product.sku,
        "title": title,
        "price": draft.calculated_price if draft else None,
        "quantity": _supplier_default_quantity(settings, supplier),
        "condition": item_condition,
        "description": description,
        "item_specifics": item_specifics,
        "image_urls": clean_image_urls,
        "local_image_paths": local_image_paths,
        "manual_image_paths": manual_image_paths,
        "image_upload_status": image_upload_status,
        "source_url": supplier.source_url if supplier else None,
        "source_price": source_price,
        "source_shipping": source_shipping,
        "landed_cost": effective_landed_cost(source_price, source_shipping, settings),
        "effective_source_cost": effective_supplier_cost(source_price, settings) if source_price is not None else None,
        "gift_card_discount_enabled": bool(settings.get("default_gift_card_discount_enabled", False)),
        "gift_card_discount_percent": float(settings.get("default_gift_card_discount_percent", 0.0)),
        "competitor_price": product.competitor_price,
        "margin_price": price_decision.margin_price,
        "competitor_target_price": price_decision.competitor_target_price,
        "minimum_profit_price": price_decision.minimum_profit_price,
        "safe_competitor_price": price_decision.safe_competitor_price,
        "fee_rate_total": _fee_rate_total(settings),
        "estimated_fees": active_profit["fees"],
        "estimated_profit": active_profit["profit"],
        "minimum_profit": minimum_profit,
        "profit_gap": profit_gap if profit_gap is not None and profit_gap > 0 else 0 if profit_gap is not None else None,
        "meets_minimum_profit": active_profit["profit"] >= minimum_profit if active_profit["profit"] is not None else None,
        "margin_price_profit": margin_profit["profit"],
        "competitor_target_profit": competitor_profit["profit"],
        "minimum_profit_price_profit": minimum_profit_target_profit["profit"],
        "safe_competitor_price_profit": safe_competitor_profit["profit"],
        "warnings": warnings,
        "pricing_strategy": price_decision.strategy,
        "price_reason": price_decision.reason,
        "offers_enabled": offers_enabled,
        "listing_schedule_mode": listing_schedule_mode,
        "listing_schedule_at": listing_schedule_at,
        "shipping_cost_type": shipping_cost_type,
        "domestic_shipping_service": domestic_shipping_service,
        "buyer_shipping_cost": buyer_shipping_cost,
        "manual_posting_steps": [
            "Open eBay seller listing creation.",
            "Paste the title into the title field.",
            "Paste the calculated price into the price field.",
            "Paste the HTML description into the description field.",
            "Review and fill item specifics using item_specifics.",
            "Upload every usable downloaded local image from manual_image_paths.",
            "Disable offers unless offers_enabled is true.",
            "Schedule the listing at listing_schedule_at when a default schedule is configured.",
            f"Use item condition {item_condition} during eBay prelist.",
            "Use flat domestic shipping with buyer_shipping_cost and domestic_shipping_service.",
            "Review category, item specifics, shipping, returns, and quantity before publishing.",
        ],
    }


def _default_listing_schedule_at(settings: dict[str, float | bool | str]) -> str | None:
    if str(settings.get("default_listing_schedule_mode", "now")) != "scheduled":
        return None
    days_ahead = int(float(settings.get("default_listing_schedule_days_ahead", 0)))
    time_value = str(settings.get("default_listing_schedule_time", "09:00"))
    if not re.match(r"^([01][0-9]|2[0-3]):[0-5][0-9]$", time_value):
        time_value = "09:00"
    hour, minute = [int(part) for part in time_value.split(":")]
    scheduled = datetime.utcnow() + timedelta(days=days_ahead)
    scheduled = scheduled.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled <= datetime.utcnow():
        scheduled = scheduled + timedelta(days=1)
    return scheduled.isoformat()


def _uploadable_local_image_paths(local_image_paths: list[str]) -> list[str]:
    uploadable: list[str] = []
    for local_path in local_image_paths:
        dimensions = _local_image_dimensions(local_path)
        if dimensions is None:
            try:
                if _project_path(local_path).stat().st_size >= 10_000:
                    uploadable.append(local_path)
            except OSError:
                continue
            continue
        width, height = dimensions
        if width >= 500 and height >= 500:
            uploadable.append(local_path)
    return uploadable or local_image_paths[:1]


def _local_image_dimensions(local_path: str) -> tuple[int, int] | None:
    path = _project_path(local_path)
    if not path.exists():
        return None
    try:
        data = path.read_bytes()[:4096]
    except OSError:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        try:
            return _jpeg_dimensions(path)
        except OSError:
            return None
    return None


def _jpeg_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[index : index + 2], "big")
        if segment_length < 2:
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 > len(data):
                return None
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return width, height
        index += segment_length
    return None


def build_ebay_api_payload(db: Session, product_id: int) -> dict | None:
    package = build_ebay_listing_package(db, product_id)
    if package is None:
        return None
    settings = read_pricing_settings(db)
    missing = [
        key
        for key in [
            "ebay_category_id",
            "ebay_merchant_location_key",
            "ebay_fulfillment_policy_id",
            "ebay_payment_policy_id",
            "ebay_return_policy_id",
        ]
        if not settings.get(key)
    ]
    inventory_item_payload = {
        "availability": {
            "shipToLocationAvailability": {
                "quantity": package["quantity"],
            }
        },
        "condition": "NEW",
        "product": {
            "title": package["title"],
            "description": package["description"],
            "imageUrls": package["image_urls"],
            "aspects": {key: [value] for key, value in package["item_specifics"].items()},
        },
    }
    offer_payload = {
        "sku": package["sku"],
        "marketplaceId": settings["ebay_marketplace_id"],
        "format": "FIXED_PRICE",
        "availableQuantity": package["quantity"],
        "categoryId": settings["ebay_category_id"],
        "listingDescription": package["description"],
        "listingPolicies": {
            "fulfillmentPolicyId": settings["ebay_fulfillment_policy_id"],
            "paymentPolicyId": settings["ebay_payment_policy_id"],
            "returnPolicyId": settings["ebay_return_policy_id"],
        },
        "merchantLocationKey": settings["ebay_merchant_location_key"],
        "pricingSummary": {
            "price": {
                "currency": "USD",
                "value": f"{package['price']:.2f}" if package["price"] is not None else None,
            }
        },
    }
    if package.get("listing_schedule_at"):
        offer_payload["listingStartDate"] = package["listing_schedule_at"]
    return {
        "product_id": package["product_id"],
        "sku": package["sku"],
        "environment": str(settings.get("ebay_environment", "sandbox")),
        "inventory_item_endpoint": f"PUT /sell/inventory/v1/inventory_item/{package['sku']}",
        "offer_endpoint": "POST /sell/inventory/v1/offer",
        "publish_endpoint_template": "POST /sell/inventory/v1/offer/{offerId}/publish",
        "inventory_item_payload": inventory_item_payload,
        "offer_payload": offer_payload,
        "publish_payload": {
            "note": "Create the offer first; use the returned offerId in the publish endpoint.",
        },
        "missing_publish_requirements": missing,
    }


def build_ebay_manual_macro(db: Session, product_id: int) -> dict | None:
    package = build_ebay_listing_package(db, product_id)
    readiness = build_listing_readiness(db, product_id) if package is not None else None
    if package is None or readiness is None:
        return None
    return {
        "product_id": package["product_id"],
        "sku": package["sku"],
        "title": package["title"],
        "price": package["price"],
        "manual_ready": readiness["manual_ready"],
        "missing_manual": readiness["missing_manual"],
        "warnings": readiness["warnings"],
        "script": _macro_template(package),
    }


def build_listing_readiness(db: Session, product_id: int) -> dict | None:
    package = build_ebay_listing_package(db, product_id)
    if package is None:
        return None
    api_payload = build_ebay_api_payload(db, product_id)
    if api_payload is None:
        return None

    has_title = bool(str(package["title"] or "").strip())
    has_price = package["price"] is not None and package["price"] > 0
    has_description = bool(str(package["description"] or "").strip())
    image_count = len(package["image_urls"])
    downloaded_image_count = len(package["local_image_paths"])
    has_images = image_count > 0 and downloaded_image_count == image_count
    has_source_url = bool(package["source_url"])
    has_source_price = package["source_price"] is not None and package["source_price"] > 0
    has_source_shipping = package["source_shipping"] is not None and package["source_shipping"] >= 0

    checks = {
        "title": has_title,
        "price": has_price,
        "description": has_description,
        "images": has_images,
        "source_url": has_source_url,
        "source_price": has_source_price,
        "source_shipping": has_source_shipping,
        "ebay_category_id": "ebay_category_id" not in api_payload["missing_publish_requirements"],
        "ebay_merchant_location_key": "ebay_merchant_location_key" not in api_payload["missing_publish_requirements"],
        "ebay_fulfillment_policy_id": "ebay_fulfillment_policy_id" not in api_payload["missing_publish_requirements"],
        "ebay_payment_policy_id": "ebay_payment_policy_id" not in api_payload["missing_publish_requirements"],
        "ebay_return_policy_id": "ebay_return_policy_id" not in api_payload["missing_publish_requirements"],
    }
    manual_labels = {
        "title": "listing title",
        "price": "calculated listing price",
        "description": "listing description",
        "images": "all product images downloaded",
        "source_url": "supplier/source URL",
        "source_price": "supplier/source price",
        "source_shipping": "supplier/source shipping",
    }
    missing_manual = [label for key, label in manual_labels.items() if not checks[key]]
    missing_api = list(missing_manual) + api_payload["missing_publish_requirements"]

    warnings: list[str] = []
    if image_count and downloaded_image_count < image_count:
        warnings.append(
            f"Only {downloaded_image_count}/{image_count} image(s) are downloaded locally"
        )
    warnings.extend(package.get("warnings", []))
    margin_price = package["margin_price"]
    competitor_target = package["competitor_target_price"]
    if (
        package["pricing_strategy"] == "competitor"
        and margin_price is not None
        and competitor_target is not None
        and competitor_target < margin_price
    ):
        warnings.append(
            f"Competitor target ${competitor_target:.2f} is below margin price ${margin_price:.2f}; review profit before publishing"
        )

    return {
        "product_id": package["product_id"],
        "sku": package["sku"],
        "manual_ready": not missing_manual,
        "api_ready": not missing_api,
        "missing_manual": missing_manual,
        "missing_api": missing_api,
        "warnings": warnings,
        "checks": checks,
    }


def listing_item_specifics(product: Product, supplier: SupplierProduct | None) -> dict[str, str]:
    specifics: dict[str, str] = {}
    brand = _infer_brand(product.title)
    if brand:
        specifics["Brand"] = brand
    model = _infer_model_number(product.title, supplier.source_url if supplier else None)
    if model:
        specifics["MPN"] = model
    elif supplier and supplier.supplier_sku:
        specifics["MPN"] = supplier.supplier_sku
    return specifics


def _infer_brand(title: str) -> str | None:
    clean_title = re.sub(r"\s+", " ", title or "").strip()
    if not clean_title:
        return None
    known_prefixes = [
        "Columbia Forest Products",
        "Ornamental Mouldings",
        "True Blue",
        "Milwaukee",
        "HDX",
    ]
    lower_title = clean_title.lower()
    for prefix in known_prefixes:
        if lower_title.startswith(prefix.lower()):
            return prefix

    tokens = clean_title.split()
    brand_tokens: list[str] = []
    stop_words = {
        "in",
        "ft",
        "gal",
        "gallon",
        "qt",
        "oz",
        "pack",
        "count",
        "with",
        "for",
    }
    for token in tokens:
        normalized = re.sub(r"[^A-Za-z0-9]", "", token).lower()
        if not normalized or normalized in stop_words or any(char.isdigit() for char in token):
            break
        brand_tokens.append(token)
        if len(brand_tokens) >= 3:
            break
    return " ".join(brand_tokens) if brand_tokens else None


def _infer_model_number(title: str, source_url: str | None) -> str | None:
    candidates: list[str] = []
    if source_url:
        path_parts = [unquote(part) for part in urlparse(source_url).path.split("/") if part]
        if len(path_parts) > 1:
            candidates.append(path_parts[1])
    candidates.append(title or "")
    ignored = {"HDX", "USB", "LED", "FPR", "REDLITHIUM"}
    model_candidates: list[str] = []
    for text in candidates:
        for match in re.finditer(r"\b[A-Z0-9][A-Z0-9-]{4,}\b", text):
            value = match.group(0).strip("-")
            if value in ignored:
                continue
            if not any(char.isdigit() for char in value):
                continue
            if re.fullmatch(r"\d+(?:-\d+)*", value):
                continue
            model_candidates.append(value)
        if model_candidates:
            return model_candidates[-1]
    return None


def export_ebay_listing_files(db: Session, product_id: int) -> dict | None:
    package = build_ebay_listing_package(db, product_id)
    if package is None:
        return None
    api_payload = build_ebay_api_payload(db, product_id)
    sku = _safe_filename(package["sku"])
    export_dir = Path("exports") / "ebay" / sku
    export_dir.mkdir(parents=True, exist_ok=True)

    listing_json_path = export_dir / "listing.json"
    description_html_path = export_dir / "description.html"
    image_manifest_path = export_dir / "images.txt"
    macro_script_path = export_dir / "ebay_manual_macro_template.js"
    api_payload_path = export_dir / "ebay_inventory_api_payload.json"
    zip_path = export_dir.with_suffix(".zip")

    listing_json_path.write_text(json.dumps(package, indent=2), encoding="utf-8")
    description_html_path.write_text(package["description"], encoding="utf-8")
    image_manifest_path.write_text(
        "\n".join(
            [
                "Local images to upload:",
                *(package["manual_image_paths"] or ["None downloaded yet"]),
                "",
                "Source image URLs:",
                *package["image_urls"],
            ]
        ),
        encoding="utf-8",
    )
    macro_script_path.write_text(_macro_template(package), encoding="utf-8")
    api_payload_path.write_text(json.dumps(api_payload, indent=2), encoding="utf-8")

    files = [listing_json_path, description_html_path, image_manifest_path, macro_script_path, api_payload_path]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
        for local_path in package["local_image_paths"]:
            image_path = _project_path(local_path)
            if image_path.exists():
                archive.write(image_path, arcname=f"images/{image_path.name}")

    return {
        "product_id": product_id,
        "export_dir": str(export_dir),
        "listing_json_path": str(listing_json_path),
        "description_html_path": str(description_html_path),
        "image_manifest_path": str(image_manifest_path),
        "macro_script_path": str(macro_script_path),
        "api_payload_path": str(api_payload_path),
        "zip_path": str(zip_path),
        "files": [str(path) for path in [*files, zip_path]],
    }


def _extract_json_ld(html_text: str) -> dict:
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text, re.S | re.I):
        try:
            parsed = json.loads(html.unescape(raw.strip()))
        except json.JSONDecodeError:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            item_type = item.get("@type") if isinstance(item, dict) else None
            if isinstance(item, dict) and (item_type == "Product" or (isinstance(item_type, list) and "Product" in item_type)):
                return item
    return {}


def _meta(html_text: str, name: str) -> str | None:
    if not html_text:
        return None
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(name)}["\']',
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, re.I)
        if match:
            return html.unescape(match.group(1)).strip()
    return None


def _first_text(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return re.sub(r"\s+", " ", value).strip()
    return "Imported Product"


def _title_from_url(url: str) -> str:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    slug = path_parts[1] if len(path_parts) > 1 and path_parts[0] == "p" else path_parts[-1]
    slug = re.sub(r"-\d+$", "", slug)
    title = unquote(slug).replace("-", " ").strip().title()
    return re.sub(r"\bHdx\b", "HDX", title)


def _sku_from_url(url: str) -> str | None:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if path_parts:
        return path_parts[-1]
    return None


def _price_from_structured(data: dict) -> float | None:
    offers = data.get("offers") if isinstance(data, dict) else None
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if isinstance(offers, dict):
        return _to_float(offers.get("price") or offers.get("lowPrice"))
    return None


def _price_from_text(html_text: str) -> float | None:
    if not html_text:
        return None
    for pattern in [r'"price"\s*:\s*"?(\d+(?:\.\d{1,2})?)"?', r'\$(\d{1,4}\.\d{2})']:
        match = re.search(pattern, html_text)
        if match:
            return _to_float(match.group(1))
    return None


def _images_from_structured(data: dict) -> list[str]:
    image = data.get("image") if isinstance(data, dict) else None
    if isinstance(image, str):
        return [image]
    if isinstance(image, list):
        return [item for item in image if isinstance(item, str)]
    return []


def _images_from_html(html_text: str) -> list[str]:
    if not html_text:
        return []
    images = re.findall(r'https?://[^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?', html_text, re.I)
    return [html.unescape(image) for image in images if "homedepot" in image or "scene7" in image]


def _homedepot_image_guess(url: str) -> str:
    product_id = _sku_from_url(url) or "product"
    return f"https://images.thdstatic.com/productImages/{product_id}.jpg"


def _generate_description(title: str, structured: dict, html_text: str) -> str:
    structured_description = structured.get("description") if isinstance(structured, dict) else None
    description = str(structured_description).strip() if structured_description else _meta(html_text, "description")
    bullets = _extract_bullets(html_text)
    text = "\n".join([line for line in [description, *bullets] if line])
    return _description_from_capture(title, text)


def _description_from_capture(
    title: str,
    description: str | None,
    settings: dict[str, float | bool | str] | None = None,
) -> str:
    if description and "data-autozs-template" in description:
        return description
    if description and ("<p" in description or "<ul" in description or "<br" in description):
        return _apply_description_template(title, description, settings)
    lines = _clean_description_lines(description)
    if not lines:
        lines = ["Product details are summarized from the source listing for a clean marketplace draft."]

    title_text = _ebay_title(title)
    intro = lines[0]
    bullets = _dedupe(lines[1:])

    if not bullets:
        bullets = [
            "Source product details captured for the listing draft.",
            "Images and pricing are managed separately in the dashboard.",
        ]

    highlight_bullets = bullets[:6]
    detail_bullets = bullets[6:12]
    if not detail_bullets:
        detail_bullets = [
            "Condition: New",
            "Review dimensions, color, and compatibility against the source listing before publishing.",
        ]

    highlight_html = "".join(f"<li>{html.escape(bullet)}</li>" for bullet in highlight_bullets)
    detail_html = "".join(f"<li>{html.escape(bullet)}</li>" for bullet in detail_bullets)
    content = (
        f"<h2>{html.escape(title_text)}</h2>"
        "<h3>Overview</h3>"
        f"<p>{html.escape(intro)}</p>"
        "<h3>Highlights</h3>"
        f"<ul>{highlight_html}</ul>"
        "<h3>Details</h3>"
        f"<ul>{detail_html}</ul>"
        "<p>Please review all item specifics, shipping settings, returns, and compatibility before publishing.</p>"
    )
    return _apply_description_template(title, content, settings)


def _apply_description_template(
    title: str,
    content: str,
    settings: dict[str, float | bool | str] | None,
) -> str:
    if not settings or not bool(settings.get("description_template_enabled", True)):
        return content
    if "data-autozs-template" in content:
        return content
    brand = html.escape(str(settings.get("description_template_brand") or "AutoZS").strip())
    template_name = html.escape(str(settings.get("description_template_name") or "AutoZS Home Improvement").strip())
    about = html.escape(str(settings.get("description_template_about") or "").strip())
    shipping = html.escape(str(settings.get("description_template_shipping") or "").strip())
    returns = html.escape(str(settings.get("description_template_returns") or "").strip())
    satisfaction = html.escape(str(settings.get("description_template_satisfaction") or "").strip())
    title_text = html.escape(_ebay_title(title))
    policy_sections = [
        ("About us", about),
        ("Shipping", shipping),
        ("Returns", returns),
        ("Satisfaction", satisfaction),
    ]
    policy_html = "".join(
        (
            '<div style="flex:1 1 210px;border:1px solid #d9e2dd;border-radius:6px;padding:14px;'
            'background:#ffffff;">'
            f'<h3 style="margin:0 0 8px;color:#176f62;font-size:16px;">{heading}</h3>'
            f'<p style="margin:0;color:#46524c;line-height:1.55;">{body}</p></div>'
        )
        for heading, body in policy_sections
        if body
    )
    return (
        '<div data-autozs-template="1" style="max-width:900px;margin:0 auto;background:#f6f8f7;'
        'border:1px solid #d9e2dd;font-family:Arial,Helvetica,sans-serif;color:#18201b;">'
        '<div style="background:#14201c;color:#ffffff;padding:24px 28px;">'
        f'<div style="font-size:26px;font-weight:800;">{brand}</div>'
        f'<div style="margin-top:4px;color:#a9d8cf;font-size:13px;">{template_name}</div></div>'
        '<div style="display:flex;flex-wrap:wrap;background:#55b7a7;color:#ffffff;">'
        '<div style="flex:1 1 160px;padding:13px 18px;text-align:center;font-weight:700;">Fast shipping</div>'
        '<div style="flex:1 1 160px;padding:13px 18px;text-align:center;font-weight:700;">30-day support</div>'
        '<div style="flex:1 1 160px;padding:13px 18px;text-align:center;font-weight:700;">Responsive service</div>'
        '</div>'
        '<div style="padding:26px 28px;">'
        f'<h1 style="margin:0 0 20px;font-size:24px;line-height:1.3;">{title_text}</h1>'
        f'<div style="background:#ffffff;border:1px solid #d9e2dd;border-radius:6px;padding:20px;'
        f'line-height:1.6;">{content}</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:18px;">{policy_html}</div>'
        '</div></div>'
    )


def _matching_blacklist_keyword(title: str, settings: dict[str, float | bool | str]) -> str | None:
    try:
        keywords = json.loads(str(settings.get("keyword_blacklist_json") or "[]"))
    except json.JSONDecodeError:
        return None
    normalized_title = title.casefold()
    for keyword in keywords if isinstance(keywords, list) else []:
        normalized_keyword = str(keyword).strip().casefold()
        if normalized_keyword and normalized_keyword in normalized_title:
            return str(keyword).strip()
    return None


def _supplier_default_quantity(
    settings: dict[str, float | bool | str],
    supplier: SupplierProduct | None,
) -> int:
    try:
        suppliers = json.loads(str(settings.get("supplier_settings_json") or "{}"))
    except json.JSONDecodeError:
        return 1
    supplier_key = supplier.supplier if supplier else "home_depot"
    supplier_settings = suppliers.get(supplier_key, {}) if isinstance(suppliers, dict) else {}
    try:
        return max(1, min(int(supplier_settings.get("default_quantity", 1)), 99))
    except (TypeError, ValueError):
        return 1


def _should_replace_listing_description(existing: str | None, incoming: str | None, warnings: list[str]) -> bool:
    if not existing or not existing.strip():
        return True
    if not incoming or not incoming.strip():
        return False
    source_blocked = any("blocked server-side" in warning for warning in warnings)
    if source_blocked and _description_quality_score(existing) > _description_quality_score(incoming):
        return False
    return True


def _description_quality_score(description: str | None) -> int:
    if not description:
        return 0
    score = min(len(description.strip()), 1000)
    placeholder_patterns = [
        "Product details are summarized from the source listing",
        "Source product details captured for the listing draft",
        "Images and pricing are managed separately in the dashboard",
    ]
    for pattern in placeholder_patterns:
        if pattern in description:
            score -= 350
    if "<li>" in description:
        score += 100
    if "<p" in description or "<ul" in description:
        score += 50
    return score


def _clean_description_lines(description: str | None) -> list[str]:
    if not description:
        return []
    text = re.sub(r"<br\s*/?>", "\n", description, flags=re.I)
    text = re.sub(r"</(?:p|li|div|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    lines: list[str] = []
    for raw_line in html.unescape(text).splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" -•\t")
        if not line or NOISY_DESCRIPTION_PATTERNS.search(line):
            continue
        if len(line) < 3 or len(line) > 260:
            continue
        lines.append(line)
    return _dedupe(lines)


def _extract_bullets(html_text: str) -> list[str]:
    if not html_text:
        return []
    candidates = re.findall(r'<li[^>]*>(.*?)</li>', html_text, re.S | re.I)
    cleaned = []
    for candidate in candidates:
        text = re.sub(r"<[^>]+>", " ", candidate)
        text = re.sub(r"\s+", " ", html.unescape(text)).strip()
        if 15 <= len(text) <= 220 and not NOISY_DESCRIPTION_PATTERNS.search(text):
            cleaned.append(text)
    return _dedupe(cleaned)


def _ebay_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()[:80]


def _listing_title(title: str, settings: dict[str, float | bool | str], brand: str | None = None) -> str:
    original = re.sub(r"\s+", " ", title or "").strip()
    clean = original
    suffix = _normalized_title_suffix(str(settings.get("default_title_suffix", "") or ""))
    if suffix:
        clean = _remove_title_suffix(clean, suffix)
    if brand and bool(settings.get("default_vero_remove_brand_from_title", settings.get("default_strip_brand_from_title", True))):
        stripped = re.sub(rf"^\s*{re.escape(brand)}\b[\s:-]*", "", clean, flags=re.I).strip()
        if len(stripped) >= 12:
            clean = stripped
    clean = clean or original
    if suffix and suffix.lower().strip() not in clean.lower():
        if len(clean) + len(suffix) <= 80:
            clean = f"{clean}{suffix}"
        else:
            max_base = 80 - len(suffix)
            if max_base >= 50:
                clean = f"{_truncate_title_at_word(clean, max_base)}{suffix}"
    return clean[:80]


def _normalized_title_suffix(value: str) -> str:
    suffix = re.sub(r"\s+", " ", value or "").strip()
    if suffix and not suffix.startswith(" "):
        suffix = f" {suffix}"
    return suffix


def _remove_title_suffix(title: str, suffix: str) -> str:
    if suffix and title.lower().endswith(suffix.lower()):
        return title[: -len(suffix)].rstrip()
    return title


def _truncate_title_at_word(title: str, limit: int) -> str:
    truncated = title[:limit].rstrip()
    if " " not in truncated:
        return truncated
    word_safe = truncated.rsplit(" ", 1)[0].rstrip(" ,-")
    return word_safe if len(word_safe) >= 35 else truncated


def _to_float(value: object) -> float | None:
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str | None]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _rounding_cents(settings: dict[str, float | bool | str]) -> float:
    try:
        cents = float(settings.get("default_rounding_cents", 0.99))
    except (TypeError, ValueError):
        cents = 0.99
    if cents < 0 or cents >= 1:
        return 0.99
    return round(cents, 2)


def _round_up_to_cents(value: float, cents: float) -> float:
    dollars = int(value)
    target = round(dollars + cents, 2)
    if value <= target:
        return target
    return round(dollars + 1 + cents, 2)


def _round_up_to_99(value: float) -> float:
    return _round_up_to_cents(value, 0.99)


def _fee_rate_total(settings: dict[str, float | bool | str]) -> float:
    return round(
        float(settings["default_ebay_fee_rate"])
        + float(settings["default_promoted_rate"])
        + float(settings["default_return_risk_rate"]),
        4,
    )


def _shipping_cost(value: float | None) -> float:
    if value is None or value < 0:
        return 0.0
    return float(value)


def _listing_profit_warnings(profit: float | None, minimum_profit: float, price_decision: ListingPriceDecision) -> list[str]:
    if profit is None:
        return []
    warnings: list[str] = []
    if profit < 0:
        warnings.append(f"Draft price is estimated to lose ${abs(profit):.2f}")
    elif profit < minimum_profit:
        warnings.append(f"Draft profit ${profit:.2f} is below minimum profit ${minimum_profit:.2f}")
    if price_decision.strategy == "competitor" and price_decision.margin_price is not None and price_decision.final_price is not None:
        if price_decision.final_price < price_decision.margin_price:
            warnings.append(
                f"Competitor strategy selected a draft price ${price_decision.final_price:.2f} below margin target ${price_decision.margin_price:.2f}"
            )
    return warnings


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "listing"


def _macro_template(package: dict) -> str:
    return f"""// eBay manual posting macro template.
// Run only in your own browser session after opening eBay's listing creation page.
// This does not bypass login, CAPTCHA, policy checks, category requirements, or final review.

const listing = {json.dumps(package, indent=2)};

async function fillIfFound(selectors, value) {{
  for (const selector of selectors) {{
    const element = document.querySelector(selector);
    if (!element) continue;
    element.focus();
    if ("value" in element) {{
      element.value = value ?? "";
    }} else {{
      element.textContent = value ?? "";
    }}
    element.dispatchEvent(new Event("input", {{ bubbles: true }}));
    element.dispatchEvent(new Event("change", {{ bubbles: true }}));
    return true;
  }}
  return false;
}}

function normalizeLabel(value) {{
  return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}}

function cssEscape(value) {{
  if (window.CSS && CSS.escape) return CSS.escape(value);
  return String(value).replace(/["\\\\]/g, "\\\\$&");
}}

function selectorsForSpecific(label) {{
  const compact = normalizeLabel(label);
  const lower = String(label || "").toLowerCase();
  return [
    `[name="${{cssEscape(label)}}"]`,
    `[name="${{cssEscape(lower)}}"]`,
    `[name="${{cssEscape(compact)}}"]`,
    `[aria-label="${{cssEscape(label)}}"]`,
    `[aria-label*="${{cssEscape(label)}}" i]`,
    `[placeholder*="${{cssEscape(label)}}" i]`,
    `[data-testid*="${{cssEscape(compact)}}" i]`,
    `input[id*="${{cssEscape(compact)}}" i]`,
    `select[id*="${{cssEscape(compact)}}" i]`,
    `textarea[id*="${{cssEscape(compact)}}" i]`
  ];
}}

async function fillItemSpecific(label, value) {{
  if (!value) return false;
  if (await fillIfFound(selectorsForSpecific(label), value)) return true;
  const normalizedLabel = normalizeLabel(label);
  const labels = Array.from(document.querySelectorAll("label"));
  for (const labelElement of labels) {{
    if (!normalizeLabel(labelElement.textContent).includes(normalizedLabel)) continue;
    const fieldId = labelElement.getAttribute("for");
    const field =
      (fieldId && document.getElementById(fieldId)) ||
      labelElement.querySelector("input, textarea, select") ||
      labelElement.parentElement?.querySelector("input, textarea, select, [contenteditable='true']");
    if (!field) continue;
    field.focus();
    if ("value" in field) {{
      field.value = value;
    }} else {{
      field.textContent = value;
    }}
    field.dispatchEvent(new Event("input", {{ bubbles: true }}));
    field.dispatchEvent(new Event("change", {{ bubbles: true }}));
    return true;
  }}
  return false;
}}

await fillIfFound(['input[name="title"]', '#title', '[aria-label="Title"]', 'input[placeholder*="title" i]'], listing.title);
await fillIfFound(['input[name="price"]', '#price', '[aria-label="Price"]', 'input[placeholder*="price" i]'], String(listing.price ?? ""));
await fillIfFound([
  'textarea[name="description"]',
  '#description',
  '[aria-label="Description"]',
  '[contenteditable="true"][aria-label*="description" i]',
  '[contenteditable="true"]'
], listing.description);

const specificResults = {{}};
for (const [label, value] of Object.entries(listing.item_specifics || {{}})) {{
  specificResults[label] = await fillItemSpecific(label, value);
}}

console.log("Listing fields attempted. Review category, item specifics, shipping, returns, photos, and publish manually.");
console.log("Suggested item specifics:", listing.item_specifics);
console.log("Item specifics fill results:", specificResults);
if (listing.image_upload_status !== "ready") {{
  console.warn("Image upload is not ready:", listing.image_upload_status);
  console.warn("Download all product images in the dashboard before publishing this listing.");
}}
console.log("Upload these downloaded local images first:", listing.manual_image_paths);
console.log("Source image URLs for reference only:", listing.image_urls);
"""


def _download_image(product_id: int, image_url: str, sort_order: int) -> str | None:
    try:
        relative_directory = Path("downloads") / "product_images" / str(product_id)
        directory = PROJECT_ROOT / relative_directory
        directory.mkdir(parents=True, exist_ok=True)
        if image_url.startswith("data:image/"):
            header, encoded = image_url.split(",", 1)
            media_type = header.split(";")[0].removeprefix("data:")
            extension = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
                "image/gif": ".gif",
            }.get(media_type, ".img")
            path = directory / f"{sort_order + 1:02d}{extension}"
            path.write_bytes(base64.b64decode(encoded))
            return (relative_directory / path.name).as_posix()
        response = httpx.get(image_url, timeout=20, follow_redirects=True)
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200 or not content_type.startswith("image/"):
            return None
        extension = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }.get(content_type.split(";")[0], ".jpg")
        path = directory / f"{sort_order + 1:02d}{extension}"
        path.write_bytes(response.content)
        return (relative_directory / path.name).as_posix()
    except httpx.HTTPError:
        return None


def _project_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate

"""Private phone link intake. Creates drafts without fetching or publishing."""
import re
from hashlib import sha1
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import AppSetting, ListingDraft, Product, SupplierProduct
from app.services.importer import _find_product_for_source, normalize_source_url


class PhoneImportRequest(BaseModel):
    source_url: str = Field(min_length=1, max_length=4096)


def queue_phone_import(db: Session, source_url: str) -> dict:
    parsed = urlsplit(source_url.strip())
    if (parsed.scheme != "https" or parsed.hostname not in {"www.homedepot.com", "homedepot.com"}
            or parsed.username or parsed.password or parsed.port not in {None, 443}
            or not re.fullmatch(r"/p/[^/]+/\d{9}/?", parsed.path)):
        raise ValueError("Paste the full HTTPS Home Depot product link. Short links and other suppliers are not supported yet.")
    url = normalize_source_url("https://www.homedepot.com" + parsed.path.rstrip("/"))
    sku = "SRC-" + sha1(url.encode()).hexdigest()[:10].upper()
    existing = _find_product_for_source(db, url, sku)
    if existing:
        return {"product_id": existing.id, "created": False, "status": existing.status,
                "message": "This product is already in AUTOZS. Its existing data and schedule were kept."}
    product = Product(sku=sku, title=parsed.path.split("/")[-2].replace("-", " ")[:512], status="draft")
    db.add(product)
    db.flush()
    db.add(SupplierProduct(product_id=product.id, supplier="home_depot", source_url=url,
                           supplier_sku=parsed.path.rstrip("/").split("/")[-1], last_price=None, last_shipping=-1))
    db.add(ListingDraft(product_id=product.id, title=product.title, description="Review source details after desktop capture.", status="draft"))
    db.add(AppSetting(key=f"phone_import_draft_{product.id}", value="true"))
    db.commit()
    return {"product_id": product.id, "created": True, "status": "draft",
            "message": "Draft saved. The desktop worker will capture price, photos and details. Review it before scheduling."}

from hashlib import sha1

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.domain import ListingDraft, Product, ProductImage, ProductStatus, SupplierProduct
from app.services import importer


def test_clean_import_uses_richer_legacy_capture_for_same_normalized_source(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    clean_url = "https://www.homedepot.com/p/HDX-Cached-Capture/331012931"
    legacy_url = f"{clean_url}?auto_download_test=1"
    clean_sku = f"SRC-{sha1(clean_url.encode()).hexdigest()[:10].upper()}"
    try:
        weak = Product(
            sku=clean_sku,
            title="Weak Clean Product",
            status=ProductStatus.monitoring.value,
            desired_profit=8.0,
            risk_buffer=3.0,
            ebay_fee_rate=0.1325,
            promoted_rate=0.0,
            return_risk_rate=0.02,
            undercut_amount=0.2,
        )
        rich = Product(
            sku="SRC-LEGACY-CAPTURE",
            title="Rich Legacy Product",
            status=ProductStatus.monitoring.value,
            desired_profit=8.0,
            risk_buffer=3.0,
            ebay_fee_rate=0.1325,
            promoted_rate=0.0,
            return_risk_rate=0.02,
            undercut_amount=0.2,
        )
        db.add_all([weak, rich])
        db.flush()
        db.add_all(
            [
                SupplierProduct(product_id=weak.id, supplier="home_depot", source_url=clean_url, supplier_sku="331012931", last_price=17.97, last_shipping=0.0),
                SupplierProduct(product_id=rich.id, supplier="home_depot", source_url=legacy_url, supplier_sku="331012931", last_price=17.97, last_shipping=0.0),
                ProductImage(product_id=weak.id, image_url="https://images.thdstatic.com/productImages/331012931.jpg", sort_order=0),
                ProductImage(product_id=rich.id, image_url="https://images.thdstatic.com/productImages/rich-front.jpg", local_path="downloads/product_images/2/01.jpg", sort_order=0),
                ProductImage(product_id=rich.id, image_url="https://images.thdstatic.com/productImages/rich-side.jpg", local_path="downloads/product_images/2/02.jpg", sort_order=1),
                ListingDraft(product_id=weak.id, title="Weak Clean Product", description="Product details are summarized from the source listing for a clean marketplace draft."),
                ListingDraft(
                    product_id=rich.id,
                    title="Rich Legacy Product",
                    description="<p>Captured details are ready for eBay.</p><ul><li>Real browser-captured bullet</li></ul>",
                ),
            ]
        )
        db.commit()

        def blocked_source_fetch(source_url: str, source_price_override: float | None = None) -> importer.ImportedProductData:
            return importer.ImportedProductData(
                source_url=source_url,
                supplier="home_depot",
                supplier_sku="331012931",
                title="HDX Cached Capture",
                source_price=None,
                description="Fallback description",
                image_urls=["https://images.thdstatic.com/productImages/331012931.jpg"],
                warnings=[
                    "Home Depot blocked server-side price capture; use browser capture or fill source price in Products",
                    "Image URL was inferred from the Home Depot product id",
                    "No source price captured; margin and draft price need source price before listing",
                ],
            )

        monkeypatch.setattr(importer, "extract_product_data", blocked_source_fetch)

        products, warnings = importer.import_products(db, [clean_url], competitor_price=21.49)

        assert products[0].id == rich.id
        assert products[0].sku == rich.sku
        assert [image.image_url for image in products[0].images] == [
            "https://images.thdstatic.com/productImages/rich-front.jpg",
            "https://images.thdstatic.com/productImages/rich-side.jpg",
        ]
        assert "Real browser-captured bullet" in products[0].listing_drafts[0].description
        assert "Fallback description" not in products[0].listing_drafts[0].description
        assert db.get(Product, weak.id).status == ProductStatus.deleted.value
        assert "No source price captured" not in " ".join(warnings)
        assert "Image URL was inferred" not in " ".join(warnings)
    finally:
        db.close()


def test_import_uses_selected_supplier_override(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    source_url = "https://example.com/product/test-item"
    try:
        def source_fetch(source: str, source_price_override: float | None = None) -> importer.ImportedProductData:
            return importer.ImportedProductData(
                source_url=source,
                supplier="source_site",
                supplier_sku="test-item",
                title="Test Item",
                source_price=19.99,
                description="Test item details",
                image_urls=[],
                warnings=[],
            )

        monkeypatch.setattr(importer, "extract_product_data", source_fetch)

        products, warnings = importer.import_products(db, [source_url], supplier_override="walmart")

        assert not warnings
        assert products[0].supplier_products[0].supplier == "walmart"
    finally:
        db.close()

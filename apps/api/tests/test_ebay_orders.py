import base64

from datetime import datetime

from app.core.database import get_db
from app.main import app
from app.models.domain import EbayListing, ListingJob, SupplierProduct
from app.services.orders import reconcile_sold_listing_replacements


def _captured_product(client):
    return client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/First-Real-Sale/123456789",
            "title": "First Real Sale Product",
            "source_price": 12.0,
            "source_shipping": 0.0,
            "description": "A product used to test Seller Hub order imports.",
            "image_urls": "https://images.thdstatic.com/productImages/first-sale.jpg",
        },
    ).json()


def _orders_csv() -> bytes:
    return (
        ",,,,,,,,,,,,,\n"
        "Order Number,Buyer Username,Ship To Name,Ship To Address 1,Ship To Address 2,Ship To City,Ship To State,Ship To Zip,Ship To Country,Item Number,Item Title,Custom Label,Quantity,"
        "Sold For,Shipping And Handling,Total Price,Paid On Date,Ship By Date,"
        "Shipped On Date,Shipping Service,Tracking Number\n"
        "12-34567-89012,first-buyer,Jamie Rivera,123 Example Ave,Apt 4,Lakewood,CO,80226,United States,800123456789,First Real Sale Product,,1,"
        "$19.53,$0.00,$19.53,Jul-27-26,Jul-29-26,,"
        "USPS Ground Advantage,\n"
        "1,record(s) downloaded,\n"
    ).encode()


def test_chrome_order_report_import_is_idempotent_and_matches_listing(client) -> None:
    product = _captured_product(client)
    marked = client.post(
        f"/products/{product['id']}/mark-listed",
        json={
            "listing_id": "800123456789",
            "account_id": "a.m.anim-59",
            "environment": "manual",
            "quantity": 1,
            "status": "active",
        },
    )
    assert marked.status_code == 200

    queued = client.post("/orders/sync?account_key=a.m.anim-59").json()
    claimed = client.post("/orders/sync/next?account_key=a.m.anim-59").json()
    assert claimed["id"] == queued["id"]
    assert claimed["status"] == "running"
    assert "autozs_report_type=orders" in claimed["runner_url"]

    payload = {
        "account_key": "a.m.anim-59",
        "run_id": claimed["id"],
        "filename": "ebay-orders-a.m.anim-59-run-1.csv",
        "report_base64": base64.b64encode(_orders_csv()).decode(),
    }
    first = client.post("/orders/import-file", json=payload)
    assert first.status_code == 200, first.text
    assert first.json() == {
        "orders_seen": 1,
        "orders_upserted": 1,
        "unmatched_items": 0,
        "run_id": claimed["id"],
    }

    orders = client.get("/orders").json()
    assert len(orders) == 1
    assert orders[0]["ebay_order_id"] == "12-34567-89012"
    assert orders[0]["buyer_username"] == "first-buyer"
    assert orders[0]["recipient_name"] == "Jamie Rivera"
    assert orders[0]["shipping_address_line1"] == "123 Example Ave"
    assert orders[0]["shipping_address_line2"] == "Apt 4"
    assert orders[0]["shipping_city"] == "Lakewood"
    assert orders[0]["shipping_state"] == "CO"
    assert orders[0]["shipping_postal_code"] == "80226"
    assert orders[0]["shipping_country"] == "United States"
    assert orders[0]["account_id"] == "a.m.anim-59"
    assert orders[0]["total"] == 19.53
    assert orders[0]["items"][0]["product_id"] == product["id"]
    assert orders[0]["items"][0]["quantity"] == 1
    assert orders[0]["items"][0]["sale_price"] == 19.53
    assert orders[0]["fulfillment_tasks"][0]["status"] == "open"
    listings = client.get("/ebay/listings").json()
    assert listings[0]["status"] == "ended"
    assert listings[0]["quantity"] == 0
    restock_jobs = client.get("/listing-jobs").json()
    assert len(restock_jobs) == 1
    assert restock_jobs[0]["product_id"] == product["id"]
    assert restock_jobs[0]["action"] == "publish"
    assert restock_jobs[0]["status"] == "queued"
    assert "automatic restock" in restock_jobs[0]["message"]

    repeated = client.post("/orders/import-file", json=payload)
    assert repeated.status_code == 200
    repeated_orders = client.get("/orders").json()
    assert len(repeated_orders) == 1
    assert len(repeated_orders[0]["items"]) == 1
    assert len(repeated_orders[0]["fulfillment_tasks"]) == 1
    assert len(client.get("/listing-jobs").json()) == 1


def test_sold_listing_reconciler_repairs_failed_publish_and_waits_for_live_confirmation(client) -> None:
    test_chrome_order_report_import_is_idempotent_and_matches_listing(client)
    session_provider = app.dependency_overrides[get_db]
    db = next(session_provider())
    try:
        first_job = db.query(ListingJob).one()
        first_job.status = "failed"
        first_job.completed_at = datetime.utcnow()
        # Seller Hub's Active Listings report can retain the item as active even
        # though its available quantity is zero.
        sold_listing = db.query(EbayListing).filter(EbayListing.listing_id == "800123456789").one()
        sold_listing.status = "active"
        supplier = db.query(SupplierProduct).filter(SupplierProduct.product_id == first_job.product_id).one()
        supplier.in_stock = True
        supplier.updated_at = datetime.utcnow()
        db.commit()

        repaired = reconcile_sold_listing_replacements(db)
        assert repaired == {
            "candidates": 1,
            "queued": 1,
            "awaiting_confirmation": 0,
            "confirmed_active": 0,
        }
        jobs = db.query(ListingJob).order_by(ListingJob.id).all()
        assert len(jobs) == 2
        assert jobs[-1].status == "queued"

        waiting = reconcile_sold_listing_replacements(db)
        assert waiting["queued"] == 0
        assert waiting["awaiting_confirmation"] == 1

        jobs[-1].status = "completed"
        db.add(
            EbayListing(
                product_id=jobs[-1].product_id,
                listing_id="800123456790",
                account_id=jobs[-1].ebay_account_key,
                environment="manual",
                quantity=1,
                status="active",
            )
        )
        db.commit()
        confirmed = reconcile_sold_listing_replacements(db)
        assert confirmed["confirmed_active"] == 1
        assert confirmed["queued"] == 0
        assert db.query(ListingJob).count() == 2
    finally:
        db.close()


def test_order_report_import_rejects_reports_without_order_numbers(client) -> None:
    content = base64.b64encode(b"Item Number,Item Title\n800123456789,No order\n").decode()
    response = client.post(
        "/orders/import-file",
        json={
            "account_key": "a.m.anim-59",
            "filename": "orders.csv",
            "report_base64": content,
        },
    )
    assert response.status_code == 422
    assert "Order Number" in response.json()["detail"]

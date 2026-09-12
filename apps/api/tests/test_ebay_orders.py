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
    assert listings[0]["status"] == "active"
    assert listings[0]["quantity"] == 0
    restock_jobs = client.get("/listing-jobs").json()
    assert restock_jobs == []

    repeated = client.post("/orders/import-file", json=payload)
    assert repeated.status_code == 200
    repeated_orders = client.get("/orders").json()
    assert len(repeated_orders) == 1
    assert len(repeated_orders[0]["items"]) == 1
    assert len(repeated_orders[0]["fulfillment_tasks"]) == 1
    assert len(client.get("/listing-jobs").json()) == 0


def test_sold_listing_reconciler_repairs_failed_publish_and_waits_for_live_confirmation(client) -> None:
    test_chrome_order_report_import_is_idempotent_and_matches_listing(client)
    session_provider = app.dependency_overrides[get_db]
    db = next(session_provider())
    try:
        listing = db.query(EbayListing).one()
        first_job = ListingJob(product_id=listing.product_id, ebay_account_key=listing.account_id, action="publish", status="failed")
        db.add(first_job)
        first_job.status = "failed"
        first_job.completed_at = datetime.utcnow()
        # Only a genuinely ended listing needs a replacement publication.
        sold_listing = db.query(EbayListing).filter(EbayListing.listing_id == "800123456789").one()
        sold_listing.status = "ended"
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

import pytest
from app.models.domain import Product
from app.services.orders import _queue_automatic_restock, _queue_replacement_publish


@pytest.mark.parametrize('exclusion', ['pruned', 'paused', 'cancelled', 'deleted'])
def test_restock_respects_product_exclusions_on_sale_and_retry(client, exclusion):
    test_chrome_order_report_import_is_idempotent_and_matches_listing(client)
    db = next(app.dependency_overrides[get_db]())
    try:
        listing = db.query(EbayListing).one()
        job = ListingJob(product_id=listing.product_id, ebay_account_key=listing.account_id, action="publish", status="failed")
        db.add(job)
        db.flush()
        job.status = 'cancelled' if exclusion == 'cancelled' else 'failed'
        product = db.get(Product, job.product_id)
        listing = db.query(EbayListing).one()
        supplier = db.query(SupplierProduct).one()
        supplier.in_stock = True
        supplier.updated_at = datetime.utcnow()
        if exclusion == 'pruned':
            listing.relist_blocked = True
        if exclusion in ('paused', 'deleted'):
            product.status = exclusion
        db.commit()
        assert not _queue_replacement_publish(db, product=product, account_key=job.ebay_account_key)
        _queue_automatic_restock(db, product=product, account_key=job.ebay_account_key,
                                 item_number=listing.listing_id, quantity=1)
        db.commit()
        assert reconcile_sold_listing_replacements(db)['queued'] == 0
        assert db.query(ListingJob).count() == 1
    finally:
        db.close()


def test_unmatched_sale_item_does_not_decrement_another_listing(client):
    product_data = _captured_product(client)
    client.post(f"/products/{product_data['id']}/mark-listed", json={
        'listing_id': '800123456789', 'account_id': 'a.m.anim-59',
        'environment': 'manual', 'quantity': 1, 'status': 'active'})
    db = next(app.dependency_overrides[get_db]())
    try:
        product = db.get(Product, product_data['id'])
        _queue_automatic_restock(db, product=product, account_key='a.m.anim-59',
                                 item_number='800999999999', quantity=1)
        db.commit()
        listing = db.query(EbayListing).one()
        assert listing.quantity == 1
        assert listing.status == 'active'
        assert db.query(ListingJob).count() == 0
    finally:
        db.close()


def test_sold_active_listing_restores_same_item_and_never_publishes(client):
    from app.models.domain import EbayRevisionJob
    from app.services.ebay_revisions import enqueue_ebay_stock_revisions
    test_chrome_order_report_import_is_idempotent_and_matches_listing(client)
    db = next(app.dependency_overrides[get_db]())
    try:
        supplier = db.query(SupplierProduct).one()
        supplier.in_stock = True
        supplier.updated_at = datetime.utcnow()
        supplier.stock_observed_at = datetime.utcnow()
        supplier.price_observed_at = datetime.utcnow()
        supplier.shipping_observed_at = datetime.utcnow()
        db.commit()
        reconcile_sold_listing_replacements(db)
        jobs = db.query(EbayRevisionJob).filter_by(action='restore_stock').all()
        assert len(jobs) == 1
        assert jobs[0].ebay_listing_id == db.query(EbayListing).one().id
        assert jobs[0].status == 'queued'
        assert db.query(ListingJob).count() == 0
        enqueue_ebay_stock_revisions(db)
        reconcile_sold_listing_replacements(db)
        assert db.query(EbayRevisionJob).filter_by(action='restore_stock').count() == 1
        assert jobs[0].status == 'queued'
        listing = db.query(EbayListing).one()
        listing.quantity = 1
        jobs[0].status = 'completed'
        db.commit()
        assert reconcile_sold_listing_replacements(db)['queued'] == 0
        assert db.query(ListingJob).count() == 0
    finally:
        db.close()


@pytest.mark.parametrize('block', ['stale', 'unknown', 'out_of_stock', 'paused', 'blocked', 'sibling', 'other_account'])
def test_sold_stock_restoration_requires_fresh_stock_and_no_duplicate(client, block):
    from datetime import timedelta
    from app.models.domain import EbayRevisionJob, Order
    test_chrome_order_report_import_is_idempotent_and_matches_listing(client)
    db = next(app.dependency_overrides[get_db]())
    try:
        listing = db.query(EbayListing).one()
        supplier = db.query(SupplierProduct).one()
        supplier.in_stock = True
        supplier.updated_at = datetime.utcnow()
        supplier.stock_observed_at = datetime.utcnow()
        supplier.price_observed_at = datetime.utcnow()
        supplier.shipping_observed_at = datetime.utcnow()
        if block == 'stale':
            supplier.stock_observed_at -= timedelta(days=2)
            supplier.price_observed_at -= timedelta(days=2)
            supplier.shipping_observed_at -= timedelta(days=2)
        if block == 'unknown': supplier.last_price = None
        if block == 'out_of_stock': supplier.in_stock = False
        if block == 'paused': db.get(Product, listing.product_id).status = 'paused'
        if block == 'blocked': listing.relist_blocked = True
        if block == 'other_account': db.query(Order).one().account_id = 'different-seller'
        if block == 'sibling':
            db.add(EbayListing(product_id=listing.product_id, account_id=listing.account_id,
                               listing_id='800123456790', status='active', quantity=1))
        db.commit()
        reconcile_sold_listing_replacements(db)
        assert db.query(EbayRevisionJob).filter_by(action='restore_stock').count() == 0
        assert db.query(ListingJob).count() == 0
    finally:
        db.close()


def test_multiple_sold_out_items_queue_only_one_restore(client):
    from app.models.domain import EbayRevisionJob
    test_chrome_order_report_import_is_idempotent_and_matches_listing(client)
    db = next(app.dependency_overrides[get_db]())
    try:
        listing = db.query(EbayListing).one()
        supplier = db.query(SupplierProduct).one()
        supplier.in_stock = True
        supplier.updated_at = datetime.utcnow()
        supplier.stock_observed_at = datetime.utcnow()
        supplier.price_observed_at = datetime.utcnow()
        supplier.shipping_observed_at = datetime.utcnow()
        db.add(EbayListing(product_id=listing.product_id, account_id=listing.account_id,
                           listing_id='800123456790', status='active', quantity=0))
        db.commit()
        reconcile_sold_listing_replacements(db)
        reconcile_sold_listing_replacements(db)
        assert db.query(EbayRevisionJob).filter_by(action='restore_stock', status='queued').count() == 1
        assert db.query(ListingJob).count() == 0
    finally:
        db.close()


def test_new_sale_prepares_one_unapproved_draft_and_import_retry_preserves_it(client):
    from app.models.domain import SupplierOrder
    _captured_product(client)
    payload = {"account_key": "a.m.anim-59", "filename": "orders.csv",
               "report_base64": base64.b64encode(_orders_csv()).decode()}
    assert client.post("/orders/import-file", json=payload).status_code == 200
    db = next(app.dependency_overrides[get_db]())
    draft = db.query(SupplierOrder).one()
    assert draft.status in {"draft", "needs_review"}
    assert draft.approved_at is None
    assert draft.attempts == 0
    draft_id = draft.id
    assert draft.order.paid_at is not None
    assert draft.order.buyer_shipping_revenue == 0
    assert client.post("/orders/import-file", json=payload).status_code == 200
    assert db.query(SupplierOrder).one().id == draft_id
    db.close()


def test_unpaid_sale_waits_then_prepares_when_payment_arrives(client):
    from app.models.domain import SupplierOrder
    from app.services.orders import import_ebay_order_report_rows, parse_ebay_order_report
    db = next(app.dependency_overrides[get_db]())
    rows = parse_ebay_order_report(_orders_csv())
    unpaid = [{key: ("" if "paid" in key.lower() else value) for key, value in row.items()} for row in rows]
    import_ebay_order_report_rows(db, rows=unpaid, account_key="test")
    assert db.query(SupplierOrder).count() == 0
    import_ebay_order_report_rows(db, rows=rows, account_key="test")
    assert db.query(SupplierOrder).count() == 1
    db.close()


@pytest.mark.parametrize("sale_a_listing", [False, True])
def test_ended_replacement_never_uses_another_accounts_listing(client, sale_a_listing):
    from datetime import timedelta
    test_chrome_order_report_import_is_idempotent_and_matches_listing(client)
    db = next(app.dependency_overrides[get_db]())
    try:
        listing = db.query(EbayListing).one()
        product_id = listing.product_id
        listing.status = "ended" if sale_a_listing else "missing"
        listing.updated_at = datetime.utcnow() - timedelta(hours=1)
        supplier = db.query(SupplierProduct).one()
        supplier.in_stock = True
        supplier.updated_at = datetime.utcnow()
        db.add(EbayListing(product_id=product_id, listing_id="other-account-item",
                           account_id="other-seller", environment="manual",
                           quantity=0, status="ended", updated_at=datetime.utcnow()))
        db.commit()
        result = reconcile_sold_listing_replacements(db)
        jobs = db.query(ListingJob).all()
        assert [job.ebay_account_key for job in jobs] == (["a.m.anim-59"] if sale_a_listing else [])
        assert result["queued"] == int(sale_a_listing)
        assert reconcile_sold_listing_replacements(db)["queued"] == 0
        assert db.query(ListingJob).count() == int(sale_a_listing)
    finally:
        db.close()


@pytest.mark.parametrize("account_a_block", [None, "active", "scheduled", "open_job"])
def test_ended_replacements_reconcile_each_sale_account_once(client, account_a_block):
    from app.models.domain import Order, OrderItem
    test_chrome_order_report_import_is_idempotent_and_matches_listing(client)
    db = next(app.dependency_overrides[get_db]())
    try:
        listing = db.query(EbayListing).one()
        listing.status = "ended"
        supplier = db.query(SupplierProduct).one()
        supplier.in_stock = True
        supplier.updated_at = datetime.utcnow()
        for account, status in [("other-seller", "imported"), ("cancelled-seller", "cancelled"),
                                ("a.m.anim-59", "imported")]:
            order = Order(ebay_order_id=f"sale-{account}", account_id=account, status=status)
            db.add(order)
            db.flush()
            db.add(OrderItem(order_id=order.id, product_id=listing.product_id, title="Sold product"))
            if account != "a.m.anim-59":
                db.add(EbayListing(product_id=listing.product_id, listing_id=f"ended-{account}",
                                   account_id=account, environment="manual", quantity=0, status="ended"))
        if account_a_block == "open_job":
            db.add(ListingJob(product_id=listing.product_id, ebay_account_key=listing.account_id,
                              action="publish", status="needs_review"))
        elif account_a_block:
            db.add(EbayListing(product_id=listing.product_id, listing_id="replacement-a",
                               account_id=listing.account_id, environment="manual", quantity=1,
                               status=account_a_block))
        db.commit()
        result = reconcile_sold_listing_replacements(db)
        assert result["candidates"] == 2
        assert result["queued"] == (2 if account_a_block is None else 1)
        queued = db.query(ListingJob).filter_by(status="queued").all()
        assert {job.ebay_account_key for job in queued} == (
            {"a.m.anim-59", "other-seller"} if account_a_block is None else {"other-seller"})
        count = db.query(ListingJob).count()
        assert reconcile_sold_listing_replacements(db)["queued"] == 0
        assert db.query(ListingJob).count() == count
    finally:
        db.close()

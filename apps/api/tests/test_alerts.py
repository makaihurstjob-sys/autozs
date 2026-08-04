from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.domain import (
    OperationalAlertStatus,
    Product,
    SourceRefreshJob,
    SourceRefreshJobStatus,
    SupplierProduct,
)
from app.services.alerts import (
    list_operational_alerts,
    refresh_operational_alerts,
    summarize_operational_alerts,
    update_operational_alert_status,
)


def make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def add_product(db, sku="SRC-ALERT", title="Alert Product"):
    product = Product(sku=sku, title=title)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def test_failed_source_refresh_creates_dismissible_alert() -> None:
    db = make_session()
    product = add_product(db)
    job = SourceRefreshJob(
        batch_key="refresh-test",
        product_id=product.id,
        status=SourceRefreshJobStatus.failed.value,
        message="Home Depot showed an error page",
    )
    db.add(job)
    db.commit()

    alerts = refresh_operational_alerts(db)
    source_alert = next(alert for alert in alerts if alert.source == "source-refresh")

    assert source_alert.status == OperationalAlertStatus.open.value
    assert "Home Depot" in source_alert.message

    dismissed = update_operational_alert_status(db, source_alert.id, OperationalAlertStatus.dismissed.value)

    assert dismissed is not None
    assert dismissed.status == OperationalAlertStatus.dismissed.value
    active_source_alerts = [alert for alert in list_operational_alerts(db, status="active") if alert.source == "source-refresh"]
    assert active_source_alerts == []


def test_stale_alert_resolves_when_condition_clears() -> None:
    db = make_session()
    product = add_product(db, sku="SRC-RESOLVE")
    job = SourceRefreshJob(
        batch_key="refresh-test",
        product_id=product.id,
        status=SourceRefreshJobStatus.failed.value,
        message="Failed",
    )
    db.add(job)
    db.commit()
    alert = next(alert for alert in refresh_operational_alerts(db) if alert.source == "source-refresh")

    job.status = SourceRefreshJobStatus.completed.value
    db.commit()
    refresh_operational_alerts(db, now=datetime.utcnow() + timedelta(minutes=1))
    resolved = [item for item in list_operational_alerts(db, status="resolved", refresh=False) if item.source == "source-refresh"]

    assert [item.id for item in resolved] == [alert.id]


def test_failed_source_refresh_alert_resolves_after_newer_success() -> None:
    db = make_session()
    product = add_product(db, sku="SRC-NEWER-SUCCESS")
    failed = SourceRefreshJob(
        batch_key="refresh-failed",
        product_id=product.id,
        status=SourceRefreshJobStatus.failed.value,
        message="Old Home Depot error",
    )
    db.add(failed)
    db.commit()
    alert = next(alert for alert in refresh_operational_alerts(db) if alert.source == "source-refresh")

    db.add(SourceRefreshJob(
        batch_key="refresh-success",
        product_id=product.id,
        status=SourceRefreshJobStatus.completed.value,
        message="Price confirmed",
    ))
    db.commit()
    active = [item for item in refresh_operational_alerts(db) if item.source == "source-refresh"]
    resolved = [item for item in list_operational_alerts(db, status="resolved", refresh=False) if item.source == "source-refresh"]

    assert active == []
    assert [item.id for item in resolved] == [alert.id]


def test_failed_source_refresh_does_not_alert_for_paused_product() -> None:
    db = make_session()
    product = add_product(db, sku="SRC-PAUSED")
    product.status = "paused"
    db.add(SourceRefreshJob(
        batch_key="refresh-paused",
        product_id=product.id,
        status=SourceRefreshJobStatus.failed.value,
        message="Source is intentionally excluded",
    ))
    db.commit()

    source_alerts = [item for item in refresh_operational_alerts(db) if item.source == "source-refresh"]

    assert source_alerts == []


def test_summary_counts_active_supplier_alert() -> None:
    db = make_session()
    product = add_product(db, sku="SRC-STOCK")
    supplier = SupplierProduct(
        product_id=product.id,
        supplier="home_depot",
        source_url="https://example.com/product",
        in_stock=False,
    )
    db.add(supplier)
    db.commit()

    alerts = refresh_operational_alerts(db)
    supplier_alerts = [alert for alert in alerts if alert.source == "supplier"]
    summary = summarize_operational_alerts(db)

    assert len(supplier_alerts) == 1
    assert summary["active"] >= 1
    assert summary["critical"] >= 1


def test_alert_routes_return_operational_feed(client) -> None:
    response = client.get("/alerts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    summary = client.get("/alerts/summary")
    assert summary.status_code == 200
    assert "active" in summary.json()


def test_replacing_a_revision_job_reuses_one_alert_per_listing() -> None:
    """Re-proposing a price for the same listing must not mint a new alert.

    Push dedupe is keyed on the alert row id, so a new alert row means another
    notification. Regression: every repricing pass retired a proposal and created a
    fresh job row, re-notifying the user about an item they had already seen -- 287
    alerts across only 61 products.
    """
    from app.models.domain import EbayListing, EbayRevisionJob, EbayRevisionJobStatus

    db = make_session()
    product = add_product(db, sku="REV-ALERT", title="Revision Product")
    listing = EbayListing(
        product_id=product.id, listing_id="800111222333", account_id="a.m.anim-59", status="active", price=20.53
    )
    db.add(listing)
    db.flush()

    first = EbayRevisionJob(
        product_id=product.id,
        ebay_listing_id=listing.id,
        target_price=24.53,
        status=EbayRevisionJobStatus.needs_review.value,
        guard_passed=True,
    )
    db.add(first)
    db.commit()
    refresh_operational_alerts(db)
    keys_after_first = {a.key for a in list_operational_alerts(db) if a.source == "ebay-revision"}
    assert len(keys_after_first) == 1

    # The next repricing pass retires that proposal and files a replacement.
    first.status = EbayRevisionJobStatus.cancelled.value
    replacement = EbayRevisionJob(
        product_id=product.id,
        ebay_listing_id=listing.id,
        target_price=26.53,
        status=EbayRevisionJobStatus.needs_review.value,
        guard_passed=True,
    )
    db.add(replacement)
    db.commit()
    refresh_operational_alerts(db)

    revision_alerts = [a for a in list_operational_alerts(db) if a.source == "ebay-revision"]
    assert {a.key for a in revision_alerts} == keys_after_first, "replacement job created a second alert row"
    assert len(revision_alerts) == 1
    assert revision_alerts[0].job_id == replacement.id, "alert should track the current proposal"

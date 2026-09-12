import json
from datetime import datetime, timedelta

import pytest

from app.models.domain import EbayAccount, EbayListing, EbayTrafficRecord
from app.services.alerts import refresh_operational_alerts
from app.services.ebay_traffic import traffic_overview
from test_alerts import make_session, add_product


def listing(db, account, *, status="active", item="item"):
    product = add_product(db, sku=account + item)
    row = EbayListing(product_id=product.id, listing_id=item, account_id=account,
                      status=status, views=12, views_measured_at=datetime.utcnow())
    db.add(row)
    db.commit()
    return row


def report(db, account, observed, *, metrics=None, item="item"):
    now = datetime.utcnow()
    row = EbayTrafficRecord(account_key=account, dimension="LISTING", dimension_value=item,
                            listing_id=item, period_start=now - timedelta(days=7), period_end=now,
                            last_updated_at=observed,
                            raw_metrics_json=json.dumps(metrics if metrics is not None else {
                                "TOTAL_IMPRESSION_TOTAL": 0, "LISTING_VIEWS_TOTAL": 0}))
    db.add(row)
    db.commit()
    return row


def stale_alerts(db):
    return {row.key for row in refresh_operational_alerts(db)
            if row.source == "ebay-traffic" and row.key.startswith("ebay-traffic:stale:")}


@pytest.mark.parametrize("observed", [None, "old", "future"])
def test_metadata_and_view_scrapes_cannot_renew_report(observed):
    db = make_session()
    try:
        listing(db, "seller-a")
        now = datetime.utcnow()
        stamp = {None: None, "old": now - timedelta(hours=40), "future": now + timedelta(days=1)}[observed]
        row = report(db, "seller-a", stamp)
        # Reading the overview enriches missing title/sku, then commit advances updated_at.
        assert traffic_overview(db)["stale"] is True
        db.commit()
        db.refresh(row)
        assert row.updated_at > now - timedelta(minutes=1)
        assert traffic_overview(db)["stale"] is True
        assert stale_alerts(db) == {"ebay-traffic:stale:seller-a"}
    finally:
        db.close()


def test_accounts_are_independent_and_recovery_resolves_only_one():
    db = make_session()
    try:
        listing(db, "seller-a", item="a")
        listing(db, "seller-b", item="b")
        assert stale_alerts(db) == {"ebay-traffic:stale:seller-a", "ebay-traffic:stale:seller-b"}
        report(db, "seller-a", datetime.utcnow() - timedelta(minutes=1), item="a")
        assert stale_alerts(db) == {"ebay-traffic:stale:seller-b"}
        assert traffic_overview(db, account="seller-a")["stale"] is False
        assert traffic_overview(db, account="seller-b")["stale"] is True
        assert traffic_overview(db)["stale"] is True
        report(db, "seller-b", datetime.utcnow() - timedelta(minutes=1), item="b")
        assert stale_alerts(db) == set()
        assert traffic_overview(db)["stale"] is False
    finally:
        db.close()


def test_views_only_report_and_ended_listing_do_not_establish_impressions():
    db = make_session()
    try:
        listing(db, "seller-a", item="active")
        listing(db, "seller-b", status="ended", item="ended")
        report(db, "seller-a", datetime.utcnow() - timedelta(minutes=1),
               metrics={"LISTING_VIEWS_TOTAL": 12}, item="active")
        assert stale_alerts(db) == {"ebay-traffic:stale:seller-a"}
        assert traffic_overview(db, account="seller-a")["stale"] is True
    finally:
        db.close()


def test_account_alias_matches_report_to_active_listing():
    db = make_session()
    try:
        db.add(EbayAccount(key="configured", account_id="seller-id", label="Seller"))
        db.commit()
        listing(db, "seller-id")
        report(db, "configured", datetime.utcnow() - timedelta(minutes=1))
        assert stale_alerts(db) == set()
        assert traffic_overview(db, account="seller-id")["stale"] is False
    finally:
        db.close()


def test_traffic_notification_defaults_on_and_can_be_disabled():
    from types import SimpleNamespace
    from app.services.push_notifications import _alert_enabled_for_subscription
    subscription = SimpleNamespace(preferences_json='{}')
    alert = SimpleNamespace(source="ebay-traffic")
    assert _alert_enabled_for_subscription(subscription, alert) is True
    subscription.preferences_json = '{"traffic_attention": false}'
    assert _alert_enabled_for_subscription(subscription, alert) is False


@pytest.mark.parametrize("value", [None, -1, float("inf"), float("nan"), "unavailable", True])
def test_invalid_metrics_do_not_establish_report_freshness(value):
    db = make_session()
    try:
        listing(db, "seller-a")
        report(db, "seller-a", datetime.utcnow() - timedelta(minutes=1),
               metrics={"TOTAL_IMPRESSION_TOTAL": value, "LISTING_VIEWS_TOTAL": 0})
        assert stale_alerts(db) == {"ebay-traffic:stale:seller-a"}
    finally:
        db.close()


@pytest.mark.parametrize("entry", [None, {}, {"value": None}, {"value": 0, "applicable": False}])
def test_api_missing_metric_values_remain_missing(client, entry):
    from test_ebay_traffic import traffic_report
    from app.core.database import get_db
    from app.main import app
    payload = traffic_report("LISTING", [("item", [])])
    payload["lastUpdatedDate"] = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
    payload["records"][0]["metricValues"] = [] if entry is None else [entry]
    response = client.post("/stats/traffic/import", json={
        "account_key": "seller-a", "account_id": "seller-a", "marketplace_id": "EBAY_US",
        "dimension": "LISTING", "report": payload,
    })
    assert response.status_code == 200
    assert client.get("/stats/traffic?account=seller-a").json()["stale"] is True
    db = next(app.dependency_overrides[get_db]())
    try:
        row = db.query(EbayTrafficRecord).one()
        assert json.loads(row.raw_metrics_json) == {}
    finally:
        db.close()

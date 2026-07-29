from __future__ import annotations

import base64
import csv
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO, TextIOWrapper
import json
import re
from typing import Any
from zipfile import BadZipFile, ZipFile

import httpx
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.domain import (
    EbayAccount,
    EbayListing,
    EbayListingViewSnapshot,
    EbaySyncRun,
    EbaySyncRunStatus,
    EbayTrafficRecord,
    Product,
)
from app.services.ebay import ebay_environment_config
from app.services.settings import read_pricing_settings


TRAFFIC_METRICS = [
    "TOTAL_IMPRESSION_TOTAL",
    "LISTING_IMPRESSION_TOTAL",
    "LISTING_IMPRESSION_SEARCH_RESULTS_PAGE",
    "LISTING_IMPRESSION_STORE",
    "LISTING_VIEWS_TOTAL",
    "LISTING_VIEWS_SOURCE_DIRECT",
    "LISTING_VIEWS_SOURCE_OFF_EBAY",
    "LISTING_VIEWS_SOURCE_OTHER_EBAY",
    "LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE",
    "LISTING_VIEWS_SOURCE_STORE",
    "CLICK_THROUGH_RATE",
    "SALES_CONVERSION_RATE",
    "TRANSACTION",
]

METRIC_FIELDS = {
    "TOTAL_IMPRESSION_TOTAL": "total_impressions",
    "LISTING_IMPRESSION_TOTAL": "listing_impressions",
    "LISTING_IMPRESSION_SEARCH_RESULTS_PAGE": "search_impressions",
    "LISTING_IMPRESSION_STORE": "store_impressions",
    "LISTING_VIEWS_TOTAL": "total_views",
    "LISTING_VIEWS_SOURCE_DIRECT": "direct_views",
    "LISTING_VIEWS_SOURCE_OFF_EBAY": "off_ebay_views",
    "LISTING_VIEWS_SOURCE_OTHER_EBAY": "other_ebay_views",
    "LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE": "search_views",
    "LISTING_VIEWS_SOURCE_STORE": "store_views",
    "CLICK_THROUGH_RATE": "click_through_rate",
    "SALES_CONVERSION_RATE": "sales_conversion_rate",
    "TRANSACTION": "transactions",
}

EXTRA_METRIC_FIELDS = {
    "PROMOTED_IMPRESSIONS": "promoted_impressions",
    "PROMOTED_LISTING_IMPRESSIONS": "promoted_impressions",
    "PROMOTED_VIEWS": "promoted_views",
    "PROMOTED_LISTING_VIEWS": "promoted_views",
    "PROMOTED_TRANSACTIONS": "promoted_transactions",
    "PROMOTED_QUANTITY_SOLD": "promoted_transactions",
    "SALES": "sales_amount",
    "SALES_AMOUNT": "sales_amount",
}

METRIC_LABELS = {
    "TOTAL_IMPRESSION_TOTAL": "Total impressions",
    "LISTING_IMPRESSION_TOTAL": "Search + Store impressions",
    "LISTING_IMPRESSION_SEARCH_RESULTS_PAGE": "Search impressions",
    "LISTING_IMPRESSION_STORE": "Store impressions",
    "LISTING_VIEWS_TOTAL": "Listing page views",
    "LISTING_VIEWS_SOURCE_DIRECT": "Direct views",
    "LISTING_VIEWS_SOURCE_OFF_EBAY": "Off-eBay views",
    "LISTING_VIEWS_SOURCE_OTHER_EBAY": "Other eBay views",
    "LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE": "Search-result views",
    "LISTING_VIEWS_SOURCE_STORE": "Store views",
    "CLICK_THROUGH_RATE": "Click-through rate",
    "SALES_CONVERSION_RATE": "Sales conversion rate",
    "TRANSACTION": "Transactions / quantity sold",
}

SELLER_HUB_CANONICAL_ALIASES = {
    "TOTAL_IMPRESSION_TOTAL": (
        "total_impressions",
        "total_listing_impressions",
        "impressions",
    ),
    "LISTING_IMPRESSION_TOTAL": (
        "total_impressions",
        "total_listing_impressions",
        "impressions",
    ),
    "LISTING_VIEWS_TOTAL": (
        "total_page_views",
        "listing_page_views",
        "page_views",
        "views",
    ),
    "LISTING_VIEWS_SOURCE_OFF_EBAY": (
        "external_site_page_views",
        "external_page_views",
        "page_views_from_external_sites",
    ),
    "CLICK_THROUGH_RATE": (
        "click_through_rate",
        "ctr",
    ),
    "SALES_CONVERSION_RATE": (
        "sales_conversion_rate",
        "conversion_rate",
    ),
    "TRANSACTION": (
        "total_quantity_sold",
        "quantity_sold",
        "transactions",
    ),
    "PROMOTED_IMPRESSIONS": (
        "promoted_impressions",
        "promoted_listings_impressions",
    ),
    "PROMOTED_VIEWS": (
        "promoted_page_views",
        "promoted_listings_page_views",
    ),
    "PROMOTED_TRANSACTIONS": (
        "promoted_quantity_sold",
        "promoted_listings_quantity_sold",
    ),
    "SALES_AMOUNT": (
        "sales",
        "sales_amount",
        "total_sales",
    ),
}


def sync_ebay_traffic(
    db: Session,
    *,
    selected_range: str = "30",
    account: str = "all",
) -> dict[str, Any]:
    days = _range_days(selected_range)
    end_day = date.today()
    start_day = end_day - timedelta(days=days - 1)
    connections = _traffic_connections(db, account)
    if not connections:
        raise ValueError(
            "No connected production eBay account has an access token. "
            "Reconnect eBay in Settings with Analytics read access."
        )

    imported = 0
    accounts_synced: list[str] = []
    for connection in connections:
        headers = {
            "Authorization": f"Bearer {connection['access_token']}",
            "Accept": "application/json",
            "Content-Language": "en-US",
        }
        base_url = ebay_environment_config(connection["environment"]).api_base_url
        imported += _fetch_dimension(
            db,
            base_url=base_url,
            headers=headers,
            account_key=connection["account_key"],
            account_id=connection["account_id"],
            marketplace_id=connection["marketplace_id"],
            dimension="DAY",
            start_day=start_day,
            end_day=end_day,
        )

        listing_ids = list(
            db.scalars(
                select(EbayListing.listing_id)
                .where(
                    EbayListing.status.in_(("active", "listed", "live", "scheduled")),
                    or_(
                        EbayListing.account_id == connection["account_id"],
                        EbayListing.account_id == connection["account_key"],
                    ),
                )
                .order_by(EbayListing.id)
            ).all()
        )
        for index in range(0, len(listing_ids), 200):
            imported += _fetch_dimension(
                db,
                base_url=base_url,
                headers=headers,
                account_key=connection["account_key"],
                account_id=connection["account_id"],
                marketplace_id=connection["marketplace_id"],
                dimension="LISTING",
                start_day=start_day,
                end_day=end_day,
                listing_ids=listing_ids[index : index + 200],
            )
        accounts_synced.append(connection["account_key"])
    db.commit()
    return {
        "records_imported": imported,
        "accounts_synced": accounts_synced,
        "period_start": start_day.isoformat(),
        "period_end": end_day.isoformat(),
    }


def import_traffic_report(
    db: Session,
    *,
    account_key: str,
    account_id: str,
    marketplace_id: str,
    payload: dict[str, Any],
    dimension: str | None = None,
) -> int:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    metric_headers = header.get("metrics") if isinstance(header.get("metrics"), list) else []
    metric_keys = [
        str(item.get("key") or "").upper()
        for item in metric_headers
        if isinstance(item, dict)
    ]
    dimension_headers = header.get("dimensionKeys") if isinstance(header.get("dimensionKeys"), list) else []
    detected_dimension = dimension or (
        str(dimension_headers[0].get("key") or "DAY")
        if dimension_headers and isinstance(dimension_headers[0], dict)
        else "DAY"
    )
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    period_start = _parse_traffic_datetime(payload.get("startDate")) or datetime.utcnow()
    period_end = _parse_traffic_datetime(payload.get("endDate")) or period_start
    last_updated_at = _parse_traffic_datetime(payload.get("lastUpdatedDate"))
    imported = 0

    for item in records:
        if not isinstance(item, dict):
            continue
        values = item.get("dimensionValues") if isinstance(item.get("dimensionValues"), list) else []
        if not values or not isinstance(values[0], dict):
            continue
        dimension_value = str(values[0].get("value") or "").strip()
        if not dimension_value:
            continue
        metric_values = item.get("metricValues") if isinstance(item.get("metricValues"), list) else []
        metrics: dict[str, float] = {}
        for index, key in enumerate(metric_keys):
            value = metric_values[index].get("value") if index < len(metric_values) and isinstance(metric_values[index], dict) else None
            metrics[key] = _metric_number(value)
        record_start = _parse_traffic_datetime(item.get("startDate"))
        record_end = _parse_traffic_datetime(item.get("endDate"))
        if detected_dimension.upper() == "DAY":
            day = _parse_dimension_day(dimension_value)
            if day:
                record_start = day
                record_end = day + timedelta(days=1) - timedelta(microseconds=1)
        measured_at = _parse_traffic_datetime(item.get("lastUpdatedDate")) or last_updated_at or datetime.utcnow()
        _upsert_traffic_record(
            db,
            account_key=account_key,
            account_id=account_id,
            marketplace_id=marketplace_id,
            dimension=detected_dimension.upper(),
            dimension_value=dimension_value,
            period_start=record_start or period_start,
            period_end=record_end or period_end,
            last_updated_at=_parse_traffic_datetime(item.get("lastUpdatedDate")) or last_updated_at,
            metrics=metrics,
        )
        if detected_dimension.upper() == "LISTING":
            _sync_listing_views_from_traffic(
                db,
                account_key=account_key,
                account_id=account_id,
                listing_id=dimension_value,
                metrics=metrics,
                measured_at=measured_at,
            )
        imported += 1
    return imported


def import_traffic_file(
    db: Session,
    *,
    account_key: str,
    filename: str,
    report_base64: str,
    run_id: int | None = None,
) -> int:
    try:
        content = base64.b64decode(report_base64, validate=True)
    except Exception as exc:
        raise ValueError("The Seller Hub Traffic report was not valid base64 data.") from exc
    text = _traffic_file_text(filename, content)
    rows = _traffic_csv_rows(text)
    if not rows:
        raise ValueError("The Seller Hub Traffic report did not contain any listing rows.")

    account = db.scalar(select(EbayAccount).where(EbayAccount.key == account_key))
    account_id = account.account_id if account else account_key
    marketplace_id = account.marketplace_id if account else "EBAY_US"
    end_day = date.today()
    start_day = end_day - timedelta(days=29)
    period_start = datetime.combine(start_day, datetime.min.time())
    period_end = datetime.combine(end_day, datetime.max.time())
    imported = 0

    for raw_row in rows:
        row = {_normalize_traffic_header(key): str(value or "").strip() for key, value in raw_row.items()}
        listing_id = _first_traffic_value(
            row,
            "listing_id",
            "item_id",
            "item_number",
            "ebay_item_id",
            "itemid",
        )
        if not listing_id:
            continue
        metrics = _seller_hub_row_metrics(row)
        record = _upsert_traffic_record(
            db,
            account_key=account_key,
            account_id=account_id,
            marketplace_id=marketplace_id,
            dimension="LISTING",
            dimension_value=listing_id,
            period_start=period_start,
            period_end=period_end,
            last_updated_at=datetime.utcnow(),
            metrics=metrics,
        )
        record.title = _first_traffic_value(row, "listing_title", "item_title", "title")[:512] or record.title
        record.sku = _first_traffic_value(row, "custom_label_sku", "custom_label", "seller_sku", "sku")[:128] or record.sku
        _sync_listing_views_from_traffic(
            db,
            account_key=account_key,
            account_id=account_id,
            listing_id=listing_id,
            metrics=metrics,
            measured_at=record.last_updated_at or datetime.utcnow(),
            sync_run_id=run_id,
        )
        imported += 1

    if not imported:
        raise ValueError("The Seller Hub Traffic report did not include recognizable eBay item IDs.")
    run = db.get(EbaySyncRun, run_id) if run_id else None
    if run is not None:
        if run.account_key != account_key:
            raise ValueError(f"Traffic report account {account_key} does not match sync run {run.account_key}.")
        run.status = EbaySyncRunStatus.completed.value
        run.phase = "completed"
        run.report_filename = filename
        run.completed_at = datetime.utcnow()
        run.listings_seen = imported
        run.listings_upserted = imported
        run.message = f"Imported Seller Hub traffic metrics for {imported} active listing(s)."
    db.commit()
    return imported


def _sync_listing_views_from_traffic(
    db: Session,
    *,
    account_key: str,
    account_id: str,
    listing_id: str,
    metrics: dict[str, float],
    measured_at: datetime,
    sync_run_id: int | None = None,
) -> bool:
    if "LISTING_VIEWS_TOTAL" not in metrics:
        return False
    listing = db.scalar(
        select(EbayListing).where(
            EbayListing.listing_id == listing_id,
            EbayListing.account_id.in_({account_key, account_id}),
        )
    )
    if listing is None:
        return False
    views = max(0, int(round(float(metrics.get("LISTING_VIEWS_TOTAL") or 0))))
    previous_views = int(listing.views or 0)
    if listing.views_measured_at == measured_at and previous_views == views:
        return False
    listing.view_delta = views - previous_views if listing.views_measured_at is not None else None
    listing.views = views
    listing.views_measured_at = measured_at
    db.flush()
    db.add(
        EbayListingViewSnapshot(
            ebay_listing_id=listing.id,
            sync_run_id=sync_run_id,
            views=views,
            captured_at=measured_at,
        )
    )
    return True


def backfill_listing_views_from_traffic(db: Session, *, account_key: str | None = None) -> int:
    query = select(EbayTrafficRecord).where(EbayTrafficRecord.dimension == "LISTING")
    if account_key:
        query = query.where(EbayTrafficRecord.account_key == account_key)
    records = list(
        db.scalars(
            query.order_by(
                EbayTrafficRecord.account_key,
                EbayTrafficRecord.dimension_value,
                EbayTrafficRecord.period_end,
                EbayTrafficRecord.updated_at,
            )
        ).all()
    )
    latest: dict[tuple[str, str], EbayTrafficRecord] = {}
    for record in records:
        latest[(record.account_key, record.listing_id or record.dimension_value)] = record
    updated = 0
    for record in latest.values():
        try:
            metrics = json.loads(record.raw_metrics_json or "{}")
        except (TypeError, ValueError):
            metrics = {}
        if _sync_listing_views_from_traffic(
            db,
            account_key=record.account_key,
            account_id=record.account_id or record.account_key,
            listing_id=record.listing_id or record.dimension_value,
            metrics=metrics,
            measured_at=record.last_updated_at or record.updated_at or datetime.utcnow(),
        ):
            updated += 1
    db.commit()
    return updated


def traffic_overview(
    db: Session,
    *,
    selected_range: str = "30",
    grain: str = "day",
    account: str = "all",
) -> dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(days=_range_days(selected_range))
    configured_account = db.scalar(
        select(EbayAccount).where(
            or_(
                EbayAccount.key == account,
                EbayAccount.account_id == account,
            )
        )
    ) if account != "all" else None
    selected_account = configured_account.key if configured_account else account
    account_aliases = {
        value
        for value in (
            selected_account,
            configured_account.account_id if configured_account else None,
        )
        if value
    }
    query = select(EbayTrafficRecord).where(EbayTrafficRecord.period_end >= cutoff)
    if selected_account != "all":
        query = query.where(
            or_(
                EbayTrafficRecord.account_key.in_(account_aliases),
                EbayTrafficRecord.account_id.in_(account_aliases),
            )
        )
    records = list(db.scalars(query.order_by(EbayTrafficRecord.period_start)).all())
    daily = [record for record in records if record.dimension == "DAY"]
    listings = [record for record in records if record.dimension == "LISTING"]

    latest_listing_records: dict[tuple[str, str], EbayTrafficRecord] = {}
    for record in listings:
        key = (record.account_key, record.listing_id or record.dimension_value)
        current = latest_listing_records.get(key)
        if current is None or record.period_end > current.period_end:
            latest_listing_records[key] = record
    listings = list(latest_listing_records.values())

    listing_models = {
        listing.listing_id: listing
        for listing in db.scalars(select(EbayListing)).all()
    }
    products = {
        product.id: product
        for product in db.scalars(select(Product)).all()
    }
    for record in listings:
        listing = listing_models.get(record.listing_id or "")
        if listing and not record.title:
            product = products.get(listing.product_id)
            record.title = product.title if product else record.listing_id
            record.sku = product.sku if product else None

    summary_source = daily if daily else listings
    summary = _sum_metrics(summary_source)
    if not summary_source:
        live_query = select(EbayListing).where(EbayListing.status.in_(("active", "listed", "live", "scheduled")))
        if selected_account != "all":
            live_query = live_query.where(EbayListing.account_id.in_(account_aliases))
        live_listings = list(db.scalars(live_query).all())
        summary["total_views"] = sum(int(item.views or 0) for item in live_listings)
        summary["listings_measured"] = sum(1 for item in live_listings if item.views_measured_at)
        latest_scrape = max((item.views_measured_at for item in live_listings if item.views_measured_at), default=None)
    else:
        summary["listings_measured"] = len(listings)
        latest_scrape = None

    summary["click_through_rate"] = _safe_rate(summary["total_views"] - summary["direct_views"] - summary["off_ebay_views"], summary["total_impressions"])
    if sum(item.click_through_rate for item in summary_source) and not summary["total_impressions"]:
        summary["click_through_rate"] = _average([item.click_through_rate for item in summary_source])
    summary["sales_conversion_rate"] = _safe_rate(summary["transactions"], summary["total_views"])
    summary["promoted_share"] = _safe_rate(summary["promoted_impressions"], summary["total_impressions"])

    trend_groups: dict[str, list[EbayTrafficRecord]] = {}
    for record in daily:
        label = record.period_start.strftime("%Y-%m") if grain == "month" else record.period_start.strftime("%Y-%m-%d")
        trend_groups.setdefault(label, []).append(record)
    trend = [{"label": label, **_sum_metrics(group)} for label, group in sorted(trend_groups.items())]
    if not trend:
        snapshot_query = (
            select(EbayListingViewSnapshot, EbayListing.account_id)
            .join(EbayListing, EbayListing.id == EbayListingViewSnapshot.ebay_listing_id)
            .where(EbayListingViewSnapshot.captured_at >= cutoff)
            .order_by(EbayListingViewSnapshot.captured_at, EbayListingViewSnapshot.id)
        )
        if selected_account != "all":
            snapshot_query = snapshot_query.where(EbayListing.account_id.in_(account_aliases))
        latest_daily_views: dict[tuple[str, int], int] = {}
        for snapshot, _account_id in db.execute(snapshot_query).all():
            label = snapshot.captured_at.strftime("%Y-%m") if grain == "month" else snapshot.captured_at.strftime("%Y-%m-%d")
            latest_daily_views[(label, snapshot.ebay_listing_id)] = int(snapshot.views or 0)
        snapshot_totals: dict[str, int] = {}
        for (label, _listing_id), views in latest_daily_views.items():
            snapshot_totals[label] = snapshot_totals.get(label, 0) + views
        trend = [
            {
                "label": label,
                "total_impressions": 0,
                "total_views": views,
                "transactions": 0,
            }
            for label, views in sorted(snapshot_totals.items())
        ]

    insights = [_listing_insight(record) for record in listings]
    best = sorted(insights, key=lambda item: (item["transactions"], item["total_views"], item["total_impressions"]), reverse=True)[:10]
    worst = sorted(
        [item for item in insights if item["total_impressions"] or item["total_views"]],
        key=lambda item: (-item["total_impressions"], item["click_through_rate"], item["sales_conversion_rate"]),
    )[:10]
    opportunities = sorted(
        insights,
        key=lambda item: item["opportunity_score"],
        reverse=True,
    )[:10]
    last_updated = max(
        [value for record in records for value in (record.last_updated_at, record.updated_at) if value]
        + ([latest_scrape] if latest_scrape else []),
        default=None,
    )
    available_metrics = sorted(
        {
            key
            for record in records
            for key in json.loads(record.raw_metrics_json or "{}").keys()
        }
        | set(TRAFFIC_METRICS)
    )
    raw_metric_totals: dict[str, float] = {}
    for record in summary_source:
        for key, value in json.loads(record.raw_metrics_json or "{}").items():
            raw_metric_totals[key] = raw_metric_totals.get(key, 0.0) + float(value or 0)
    seller_hub_records = any(
        any(str(key).startswith("SELLER_HUB_") for key in json.loads(record.raw_metrics_json or "{}"))
        for record in records
    )
    return {
        "selected_range": selected_range,
        "grain": grain,
        "selected_account": selected_account,
        "data_source": (
            "seller_hub_traffic_report"
            if seller_hub_records
            else "ebay_analytics_api"
            if records
            else "active_listing_view_scrape"
            if latest_scrape
            else "none"
        ),
        "last_updated_at": last_updated,
        "stale": last_updated is None or last_updated < datetime.utcnow() - timedelta(hours=26),
        "summary": summary,
        "trend": trend,
        "best_listings": best,
        "worst_listings": worst,
        "opportunities": opportunities,
        "source_breakdown": [
            {"key": "search", "label": "Search results", "views": summary["search_views"], "impressions": summary["search_impressions"]},
            {"key": "store", "label": "eBay Store", "views": summary["store_views"], "impressions": summary["store_impressions"]},
            {"key": "other_ebay", "label": "Other eBay pages", "views": summary["other_ebay_views"], "impressions": 0},
            {"key": "direct", "label": "Direct", "views": summary["direct_views"], "impressions": 0},
            {"key": "off_ebay", "label": "Off eBay", "views": summary["off_ebay_views"], "impressions": 0},
        ],
        "available_metrics": [
            {
                "key": key,
                "label": METRIC_LABELS.get(
                    key,
                    key.removeprefix("SELLER_HUB_").replace("_", " ").title(),
                ),
                "value": raw_metric_totals.get(key),
            }
            for key in available_metrics
        ],
    }


def _fetch_dimension(
    db: Session,
    *,
    base_url: str,
    headers: dict[str, str],
    account_key: str,
    account_id: str,
    marketplace_id: str,
    dimension: str,
    start_day: date,
    end_day: date,
    listing_ids: list[str] | None = None,
) -> int:
    filters = [
        f"marketplace_ids:{{{marketplace_id}}}",
        f"date_range:[{start_day:%Y%m%d}..{end_day:%Y%m%d}]",
    ]
    if listing_ids:
        filters.append(f"listing_ids:{{{'|'.join(listing_ids)}}}")
    response = httpx.get(
        f"{base_url}/sell/analytics/v1/traffic_report",
        params={
            "dimension": dimension,
            "filter": ",".join(filters),
            "metric": ",".join(TRAFFIC_METRICS),
        },
        headers=headers,
        timeout=45,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        raise ValueError(f"eBay Traffic API failed ({response.status_code}): {payload}") from exc
    payload = response.json()
    return import_traffic_report(
        db,
        account_key=account_key,
        account_id=account_id,
        marketplace_id=marketplace_id,
        payload=payload,
        dimension=dimension,
    )


def _upsert_traffic_record(
    db: Session,
    *,
    account_key: str,
    account_id: str,
    marketplace_id: str,
    dimension: str,
    dimension_value: str,
    period_start: datetime,
    period_end: datetime,
    last_updated_at: datetime | None,
    metrics: dict[str, float],
) -> EbayTrafficRecord:
    record = db.scalar(
        select(EbayTrafficRecord).where(
            EbayTrafficRecord.account_key == account_key,
            EbayTrafficRecord.dimension == dimension,
            EbayTrafficRecord.dimension_value == dimension_value,
            EbayTrafficRecord.period_start == period_start,
            EbayTrafficRecord.period_end == period_end,
        )
    )
    if record is None:
        record = EbayTrafficRecord(
            account_key=account_key,
            account_id=account_id,
            marketplace_id=marketplace_id,
            dimension=dimension,
            dimension_value=dimension_value,
            listing_id=dimension_value if dimension == "LISTING" else None,
            period_start=period_start,
            period_end=period_end,
        )
        db.add(record)
    record.last_updated_at = last_updated_at
    record.raw_metrics_json = json.dumps(metrics, sort_keys=True)
    for key, field in {**METRIC_FIELDS, **EXTRA_METRIC_FIELDS}.items():
        if key in metrics:
            setattr(record, field, metrics[key])
    return record


def _traffic_connections(db: Session, selected: str) -> list[dict[str, str]]:
    accounts = list(db.scalars(select(EbayAccount).where(EbayAccount.environment == "production")).all())
    result = [
        {
            "account_key": account.key,
            "account_id": account.account_id or account.key,
            "marketplace_id": account.marketplace_id or "EBAY_US",
            "environment": account.environment,
            "access_token": account.access_token,
        }
        for account in accounts
        if account.access_token
        and (selected == "all" or selected in {account.key, account.account_id})
    ]
    if result:
        return result
    settings = read_pricing_settings(db)
    access_token = str(settings.get("ebay_access_token") or "").strip()
    environment = str(settings.get("ebay_environment") or "sandbox")
    if access_token and environment == "production" and selected in {"all", "production", "manual"}:
        return [{
            "account_key": "production",
            "account_id": "production",
            "marketplace_id": str(settings.get("ebay_marketplace_id") or "EBAY_US"),
            "environment": environment,
            "access_token": access_token,
        }]
    return []


def _sum_metrics(records: list[EbayTrafficRecord]) -> dict[str, float]:
    result = {
        field: 0.0
        for field in [
            "total_impressions",
            "listing_impressions",
            "search_impressions",
            "store_impressions",
            "total_views",
            "direct_views",
            "off_ebay_views",
            "other_ebay_views",
            "search_views",
            "store_views",
            "transactions",
            "promoted_impressions",
            "promoted_views",
            "promoted_transactions",
            "sales_amount",
        ]
    }
    for record in records:
        for field in result:
            result[field] += float(getattr(record, field, 0) or 0)
    result["click_through_rate"] = _safe_rate(
        result["total_views"] - result["direct_views"] - result["off_ebay_views"],
        result["total_impressions"],
    )
    result["sales_conversion_rate"] = _safe_rate(result["transactions"], result["total_views"])
    return result


def _listing_insight(record: EbayTrafficRecord) -> dict[str, Any]:
    ctr = float(record.click_through_rate or 0)
    conversion = float(record.sales_conversion_rate or 0)
    if not ctr:
        ctr = _safe_rate(record.total_views - record.direct_views - record.off_ebay_views, record.total_impressions)
    if not conversion:
        conversion = _safe_rate(record.transactions, record.total_views)
    impression_opportunity = float(record.total_impressions or 0) * max(0.0, 0.02 - ctr)
    conversion_opportunity = float(record.total_views or 0) * max(0.0, 0.02 - conversion)
    return {
        "listing_id": record.listing_id or record.dimension_value,
        "title": record.title or record.listing_id or record.dimension_value,
        "sku": record.sku,
        "total_impressions": round(float(record.total_impressions or 0), 2),
        "total_views": round(float(record.total_views or 0), 2),
        "click_through_rate": round(ctr, 6),
        "transactions": round(float(record.transactions or 0), 2),
        "sales_conversion_rate": round(conversion, 6),
        "sales_amount": record.sales_amount,
        "opportunity_score": round(impression_opportunity + conversion_opportunity, 4),
    }


def _range_days(selected_range: str) -> int:
    return 730 if selected_range == "all" else max(1, int(selected_range or 30))


def _safe_rate(numerator: float, denominator: float) -> float:
    return round(float(numerator or 0) / float(denominator or 1), 8) if denominator else 0.0


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 8) if values else 0.0


def _metric_number(value: Any) -> float:
    if value in (None, "", "--", "N/A"):
        return 0.0
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _traffic_file_text(filename: str, content: bytes) -> str:
    if not content:
        raise ValueError("The downloaded Seller Hub Traffic report was empty.")
    if str(filename or "").lower().endswith(".zip"):
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = [name for name in archive.namelist() if name.lower().endswith((".csv", ".tsv", ".txt"))]
                if not names:
                    raise ValueError("The Traffic report ZIP did not contain a CSV or TSV file.")
                with archive.open(names[0]) as source:
                    return TextIOWrapper(source, encoding="utf-8-sig", errors="replace").read()
        except BadZipFile as exc:
            raise ValueError("The downloaded Seller Hub Traffic ZIP was invalid.") from exc
    return content.decode("utf-8-sig", errors="replace")


def _traffic_csv_rows(text: str) -> list[dict[str, str]]:
    if not text.strip():
        return []
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample.splitlines()[0] else csv.excel
    return [
        {str(key or "").strip(): str(value or "").strip() for key, value in row.items() if key is not None}
        for row in csv.DictReader(StringIO(text), dialect=dialect)
        if any(str(value or "").strip() for value in row.values())
    ]


def _normalize_traffic_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _first_traffic_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _seller_hub_row_metrics(row: dict[str, str]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    identity_fields = {
        "listing_id",
        "item_id",
        "item_number",
        "ebay_item_id",
        "itemid",
        "listing_title",
        "item_title",
        "title",
        "custom_label_sku",
        "custom_label",
        "seller_sku",
        "sku",
        "start_date",
        "end_date",
    }
    for key, value in row.items():
        if key in identity_fields or not _looks_like_traffic_number(value):
            continue
        metrics[f"SELLER_HUB_{key.upper()}"] = _seller_hub_number(value, rate="rate" in key or key == "ctr")

    for metric_key, aliases in SELLER_HUB_CANONICAL_ALIASES.items():
        value = _first_traffic_value(row, *aliases)
        if value:
            is_rate = metric_key in {"CLICK_THROUGH_RATE", "SALES_CONVERSION_RATE"}
            metrics[metric_key] = _seller_hub_number(value, rate=is_rate)

    ebay_views = _first_traffic_value(row, "ebay_views")
    external_views = _first_traffic_value(row, "external_views")
    if ebay_views or external_views:
        metrics["LISTING_VIEWS_TOTAL"] = _seller_hub_number(ebay_views) + _seller_hub_number(external_views)
        metrics["LISTING_VIEWS_SOURCE_OFF_EBAY"] = _seller_hub_number(external_views)

    search_impression_keys = [
        key
        for key in row
        if ("search" in key and "impression" in key) or key in {"top_20_search_slot_impressions", "rest_of_search_slot_impressions"}
    ]
    if search_impression_keys:
        metrics["LISTING_IMPRESSION_SEARCH_RESULTS_PAGE"] = sum(
            _seller_hub_number(row[key]) for key in search_impression_keys
        )
    return metrics


def _looks_like_traffic_number(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or text.lower() in {"n/a", "--", "-"}:
        return False
    return bool(re.fullmatch(r"[\s$€£¥+\-()\d,.%]+", text))


def _seller_hub_number(value: Any, *, rate: bool = False) -> float:
    text = str(value or "").strip()
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]+", "", text)
    try:
        number = float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0
    if negative:
        number = -abs(number)
    if rate and "%" in text:
        number /= 100
    return number


def _parse_traffic_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=None)
    except ValueError:
        return _parse_dimension_day(text)


def _parse_dimension_day(value: str) -> datetime | None:
    for pattern in ("%Y-%m-%d", "%Y%m%d", "%a %b %d %H:%M:%S GMT%z %Y"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=None)
        except ValueError:
            continue
    return None

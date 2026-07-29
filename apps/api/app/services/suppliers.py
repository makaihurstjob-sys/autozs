from __future__ import annotations

from urllib.parse import urlparse


SUPPLIER_CATALOG: tuple[dict[str, object], ...] = (
    {
        "key": "home_depot",
        "label": "Home Depot",
        "enabled": True,
        "status": "active",
        "domains": ["homedepot.com"],
        "capabilities": {
            "url_import": True,
            "browser_capture": True,
            "automatic_price_refresh": True,
            "browser_fulfillment": True,
        },
        "note": "Production supplier integration.",
    },
    {
        "key": "lowes",
        "label": "Lowe's",
        "enabled": False,
        "status": "coming_soon",
        "domains": ["lowes.com"],
        "capabilities": {
            "url_import": True,
            "browser_capture": False,
            "automatic_price_refresh": False,
            "browser_fulfillment": False,
        },
        "note": "Supplier records and UI are scaffolded; capture, refresh, and fulfillment are not enabled yet.",
    },
    {
        "key": "amazon",
        "label": "Amazon",
        "enabled": False,
        "status": "manual_only",
        "domains": ["amazon.com"],
        "capabilities": {
            "url_import": True,
            "browser_capture": False,
            "automatic_price_refresh": False,
            "browser_fulfillment": False,
        },
        "note": "Manual source records only.",
    },
    {
        "key": "walmart",
        "label": "Walmart",
        "enabled": False,
        "status": "manual_only",
        "domains": ["walmart.com"],
        "capabilities": {
            "url_import": True,
            "browser_capture": False,
            "automatic_price_refresh": False,
            "browser_fulfillment": False,
        },
        "note": "Manual source records only.",
    },
    {
        "key": "aliexpress",
        "label": "AliExpress",
        "enabled": False,
        "status": "manual_only",
        "domains": ["aliexpress.com"],
        "capabilities": {
            "url_import": True,
            "browser_capture": False,
            "automatic_price_refresh": False,
            "browser_fulfillment": False,
        },
        "note": "Manual source records only.",
    },
    {
        "key": "source_site",
        "label": "Other source",
        "enabled": False,
        "status": "manual_only",
        "domains": [],
        "capabilities": {
            "url_import": True,
            "browser_capture": False,
            "automatic_price_refresh": False,
            "browser_fulfillment": False,
        },
        "note": "Generic manual source record.",
    },
)

SUPPLIERS_BY_KEY = {str(item["key"]): item for item in SUPPLIER_CATALOG}


def supplier_catalog() -> list[dict[str, object]]:
    return [
        {
            **item,
            "domains": list(item["domains"]),
            "capabilities": dict(item["capabilities"]),
        }
        for item in SUPPLIER_CATALOG
    ]


def supplier_from_url(source_url: str) -> str:
    try:
        hostname = (urlparse(source_url).hostname or "").lower()
    except ValueError:
        return "source_site"
    for item in SUPPLIER_CATALOG:
        for domain in item["domains"]:
            if hostname == domain or hostname.endswith(f".{domain}"):
                return str(item["key"])
    return "source_site"


def supplier_supports(supplier: str, capability: str) -> bool:
    item = SUPPLIERS_BY_KEY.get(supplier)
    if item is None:
        return False
    return bool(item["capabilities"].get(capability, False))

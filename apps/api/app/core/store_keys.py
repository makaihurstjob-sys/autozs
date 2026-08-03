DEFAULT_EBAY_STORE_KEY = "a.m.anim-59"
LEGACY_DEFAULT_EBAY_STORE_KEY = "main" + "-store"


def normalize_store_key(value: str | None) -> str:
    cleaned = (value or "").strip()
    return cleaned or DEFAULT_EBAY_STORE_KEY

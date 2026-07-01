from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import AppSetting, EbayAccount


BROWSER_ACCOUNT_SETTING_KEYS = {
    "ebay_expected_username",
    "ebay_browser_username",
    "ebay_browser_url",
    "ebay_browser_marketplace",
    "ebay_browser_source",
    "ebay_browser_detected_at",
}

IGNORED_DETECTED_USERNAMES = {
    "accessibility",
    "adchoice",
    "agreement",
    "cookies",
    "privacy",
    "user agreement",
}


def read_ebay_browser_account_status(db: Session, account_key: str = "manual") -> dict:
    values = _read_browser_settings(db)
    expected_username = _expected_username(db, account_key, values)
    detected_username = values.get("ebay_browser_username", "")
    detected_at = values.get("ebay_browser_detected_at", "")
    url = values.get("ebay_browser_url", "")
    marketplace = values.get("ebay_browser_marketplace", "")
    source = values.get("ebay_browser_source", "")
    matched = _usernames_match(expected_username, detected_username) if expected_username and detected_username else False
    configured = bool(expected_username)
    can_list = configured and matched
    return {
        "account_key": account_key or "manual",
        "expected_username": expected_username,
        "detected_username": detected_username,
        "detected_at": detected_at,
        "url": url,
        "marketplace": marketplace,
        "source": source,
        "configured": configured,
        "matched": matched,
        "can_list": can_list,
        "message": _status_message(expected_username, detected_username, matched, account_key or "manual"),
    }


def update_ebay_browser_account_status(
    db: Session,
    detected_username: str | None,
    url: str | None = None,
    marketplace: str | None = None,
    source: str | None = None,
    account_key: str = "manual",
) -> dict:
    current_values = _read_browser_settings(db)
    detected = _clean_username(detected_username)
    expected = _expected_username(db, account_key, current_values)
    current_detected = current_values.get("ebay_browser_username", "")
    source_value = str(source or "chrome-extension").strip()[:64]
    if _is_ignored_detected_username(detected) or _should_preserve_matched_username(
        expected=expected,
        current_detected=current_detected,
        detected=detected,
        url=url,
        source=source_value,
    ):
        detected = current_values.get("ebay_browser_username", "")
    updates = {
        "ebay_browser_username": detected,
        "ebay_browser_url": str(url or "").strip()[:1000],
        "ebay_browser_marketplace": str(marketplace or _marketplace_from_url(url) or "").strip()[:64],
        "ebay_browser_source": source_value,
        "ebay_browser_detected_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    for key, value in updates.items():
        _write_setting(db, key, value)
    db.commit()
    return read_ebay_browser_account_status(db, account_key=account_key)


def assert_ebay_browser_account_can_list(db: Session, account_key: str = "manual") -> dict:
    status = read_ebay_browser_account_status(db, account_key=account_key)
    if not status["can_list"]:
        raise ValueError(status["message"])
    return status


def _read_browser_settings(db: Session) -> dict[str, str]:
    rows = db.scalars(select(AppSetting).where(AppSetting.key.in_(BROWSER_ACCOUNT_SETTING_KEYS))).all()
    return {row.key: row.value for row in rows}


def _write_setting(db: Session, key: str, value: str) -> None:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if setting is None:
        db.add(AppSetting(key=key, value=value))
    else:
        setting.value = value


def _expected_username(db: Session, account_key: str, values: dict[str, str]) -> str:
    if account_key and account_key != "manual":
        account = db.scalar(select(EbayAccount).where(EbayAccount.key == account_key))
        if account is not None:
            return _clean_username(account.account_id)
    return _clean_username(values.get("ebay_expected_username"))


def _clean_username(value: str | None) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("hi "):
        text = text[3:].strip()
    return text.lstrip("@").strip()


def _normalized_username(value: str | None) -> str:
    return _clean_username(value).casefold()


def _usernames_match(expected: str | None, detected: str | None) -> bool:
    return bool(expected and detected and _normalized_username(expected) == _normalized_username(detected))


def _is_ignored_detected_username(value: str | None) -> bool:
    return _normalized_username(value) in IGNORED_DETECTED_USERNAMES


def _should_preserve_matched_username(
    *,
    expected: str,
    current_detected: str,
    detected: str,
    url: str | None,
    source: str,
) -> bool:
    if source != "chrome-extension":
        return False
    if not _usernames_match(expected, current_detected):
        return False
    if not detected or _usernames_match(expected, detected):
        return False
    path = urlparse(str(url or "")).path
    return path.startswith("/lstng") or path.startswith("/sl/prelist")


def _marketplace_from_url(url: str | None) -> str:
    host = urlparse(str(url or "")).hostname or ""
    if host.endswith("ebay.com"):
        return "EBAY_US"
    if host.endswith("ebay.co.uk"):
        return "EBAY_GB"
    if host.endswith("ebay.ca"):
        return "EBAY_CA"
    if host.endswith("ebay.com.au"):
        return "EBAY_AU"
    return ""


def _status_message(expected_username: str, detected_username: str, matched: bool, account_key: str) -> str:
    if not expected_username:
        return "Set the expected eBay username in Settings before listing."
    if not detected_username:
        return "Open eBay in Chrome and let the AutoZS extension detect the signed-in username before listing."
    if not matched:
        return f"Chrome is signed in as {detected_username}, expected {expected_username} for {account_key}."
    return f"Chrome eBay account matches {expected_username}."

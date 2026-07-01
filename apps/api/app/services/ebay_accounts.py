import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import EbayAccount


CONNECTION_FIELDS = {
    "client_id": "eBay Client ID",
    "client_secret": "eBay Client Secret",
    "redirect_uri": "eBay RuName / Redirect URI",
}

POLICY_FIELDS = {
    "category_id": "eBay category ID",
    "merchant_location_key": "merchant location key",
    "fulfillment_policy_id": "fulfillment policy ID",
    "payment_policy_id": "payment policy ID",
    "return_policy_id": "return policy ID",
}


def list_ebay_accounts(db: Session) -> list[dict]:
    accounts = db.scalars(select(EbayAccount).order_by(EbayAccount.environment, EbayAccount.label)).all()
    return [serialize_ebay_account(account) for account in accounts]


def create_ebay_account(db: Session, values: dict) -> dict:
    key = _account_key(values.get("key") or values.get("label") or "ebay-account")
    key = _unique_account_key(db, key)
    account = EbayAccount(
        key=key,
        label=str(values.get("label") or key).strip(),
        account_id=str(values.get("account_id") or key).strip() or key,
    )
    _apply_account_updates(account, values)
    db.add(account)
    db.commit()
    db.refresh(account)
    return serialize_ebay_account(account)


def update_ebay_account(db: Session, account_key: str, values: dict) -> dict | None:
    account = _find_account(db, account_key)
    if account is None:
        return None
    _apply_account_updates(account, values)
    db.commit()
    db.refresh(account)
    return serialize_ebay_account(account)


def delete_ebay_account(db: Session, account_key: str) -> bool:
    account = _find_account(db, account_key)
    if account is None:
        return False
    db.delete(account)
    db.commit()
    return True


def serialize_ebay_account(account: EbayAccount) -> dict:
    missing = account_missing_fields(account)
    return {
        "id": account.id,
        "key": account.key,
        "label": account.label,
        "account_id": account.account_id,
        "environment": account.environment,
        "marketplace_id": account.marketplace_id,
        "writes_enabled": account.writes_enabled,
        "configured": not missing,
        "connected": bool(account.access_token or account.refresh_token),
        "missing": missing,
        "client_id": account.client_id,
        "redirect_uri": account.redirect_uri,
        "access_token": account.access_token,
        "refresh_token": account.refresh_token,
        "token_expires_at": account.token_expires_at,
        "refresh_token_expires_at": account.refresh_token_expires_at,
        "category_id": account.category_id,
        "merchant_location_key": account.merchant_location_key,
        "fulfillment_policy_id": account.fulfillment_policy_id,
        "payment_policy_id": account.payment_policy_id,
        "return_policy_id": account.return_policy_id,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


def account_missing_fields(account: EbayAccount) -> list[str]:
    if not account.writes_enabled:
        return []
    missing = [label for key, label in CONNECTION_FIELDS.items() if not str(getattr(account, key) or "").strip()]
    missing.extend(label for key, label in POLICY_FIELDS.items() if not str(getattr(account, key) or "").strip())
    return missing


def _apply_account_updates(account: EbayAccount, values: dict) -> None:
    string_fields = [
        "label",
        "account_id",
        "environment",
        "marketplace_id",
        "client_id",
        "redirect_uri",
        "access_token",
        "refresh_token",
        "token_expires_at",
        "refresh_token_expires_at",
        "category_id",
        "merchant_location_key",
        "fulfillment_policy_id",
        "payment_policy_id",
        "return_policy_id",
    ]
    for field in string_fields:
        if field not in values or values[field] is None:
            continue
        value = str(values[field]).strip()
        if field == "environment" and value not in {"sandbox", "production"}:
            continue
        setattr(account, field, value)
    if values.get("client_secret"):
        account.client_secret = str(values["client_secret"]).strip()
    if "writes_enabled" in values and values["writes_enabled"] is not None:
        account.writes_enabled = bool(values["writes_enabled"])
    if not account.account_id:
        account.account_id = account.key


def _find_account(db: Session, account_key: str) -> EbayAccount | None:
    return db.scalar(select(EbayAccount).where(EbayAccount.key == account_key))


def _unique_account_key(db: Session, key: str) -> str:
    base = key
    index = 2
    while _find_account(db, key) is not None:
        key = f"{base}-{index}"
        index += 1
    return key


def _account_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return key or "ebay-account"

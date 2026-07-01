import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from secrets import token_urlsafe
from urllib.parse import quote, urlencode

import httpx
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from app.models.domain import EbayListing, Product
from app.services.importer import build_ebay_api_payload, build_listing_readiness
from app.services.settings import read_pricing_settings, write_pricing_settings


DEFAULT_EBAY_SCOPES = [
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.inventory.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.account.readonly",
]


@dataclass(frozen=True)
class EbayEnvironment:
    name: str
    auth_base_url: str
    api_base_url: str
    token_url: str


def ebay_environment_config(environment: str | None) -> EbayEnvironment:
    if environment == "production":
        return EbayEnvironment(
            name="production",
            auth_base_url="https://auth.ebay.com/oauth2/authorize",
            api_base_url="https://api.ebay.com",
            token_url="https://api.ebay.com/identity/v1/oauth2/token",
        )
    return EbayEnvironment(
        name="sandbox",
        auth_base_url="https://auth.sandbox.ebay.com/oauth2/authorize",
        api_base_url="https://api.sandbox.ebay.com",
        token_url="https://api.sandbox.ebay.com/identity/v1/oauth2/token",
    )


def ebay_connection_status(db: Session) -> dict:
    settings = read_pricing_settings(db)
    env = ebay_environment_config(str(settings.get("ebay_environment", "sandbox")))
    missing = _missing_connection_fields(settings)
    auth_url = build_ebay_authorization_url(settings, state=str(settings.get("ebay_oauth_state") or "preview")) if not missing else None
    access_token = str(settings.get("ebay_access_token") or "")
    refresh_token = str(settings.get("ebay_refresh_token") or "")
    return {
        "environment": env.name,
        "configured": not missing,
        "connected": bool(access_token or refresh_token),
        "writes_enabled": bool(settings.get("ebay_enable_writes", False)),
        "missing": missing,
        "auth_url": auth_url,
        "scopes": DEFAULT_EBAY_SCOPES,
        "api_base_url": env.api_base_url,
        "token_url": env.token_url,
        "account_label": "sandbox" if env.name == "sandbox" else "production",
    }


def start_ebay_oauth(db: Session) -> dict:
    settings = read_pricing_settings(db)
    missing = _missing_connection_fields(settings)
    if missing:
        return {
            "authorization_url": "",
            "state": "",
            "scopes": DEFAULT_EBAY_SCOPES,
            "environment": str(settings.get("ebay_environment", "sandbox")),
            "missing": missing,
        }
    state = token_urlsafe(24)
    write_pricing_settings(db, {"ebay_oauth_state": state})
    settings = read_pricing_settings(db)
    return {
        "authorization_url": build_ebay_authorization_url(settings, state=state),
        "state": state,
        "scopes": DEFAULT_EBAY_SCOPES,
        "environment": str(settings.get("ebay_environment", "sandbox")),
    }


def complete_ebay_oauth(db: Session, code: str, state: str | None) -> dict:
    settings = read_pricing_settings(db)
    missing = _missing_connection_fields(settings)
    if missing:
        raise ValueError(f"Missing eBay OAuth settings: {', '.join(missing)}")
    expected_state = str(settings.get("ebay_oauth_state") or "")
    if expected_state and state != expected_state:
        raise ValueError("eBay OAuth state did not match the current connection request")

    token_payload = _request_ebay_token(
        settings,
        {
            "grant_type": "authorization_code",
            "code": code.strip(),
            "redirect_uri": str(settings.get("ebay_redirect_uri") or ""),
        },
    )
    access_expires_at = _expires_at(token_payload.get("expires_in"))
    refresh_expires_at = _expires_at(token_payload.get("refresh_token_expires_in"))
    updates: dict[str, float | bool | str | None] = {
        "ebay_access_token": str(token_payload.get("access_token") or ""),
        "ebay_token_expires_at": access_expires_at,
        "ebay_oauth_state": "",
    }
    refresh_token = str(token_payload.get("refresh_token") or "")
    if refresh_token:
        updates["ebay_refresh_token"] = refresh_token
    if refresh_expires_at:
        updates["ebay_refresh_token_expires_at"] = refresh_expires_at
    write_pricing_settings(db, updates)
    env = ebay_environment_config(str(settings.get("ebay_environment", "sandbox")))
    return {
        "environment": env.name,
        "connected": True,
        "token_type": str(token_payload.get("token_type") or "User Access Token"),
        "access_token_expires_at": access_expires_at,
        "refresh_token_expires_at": refresh_expires_at,
        "scopes": DEFAULT_EBAY_SCOPES,
    }


def refresh_ebay_access_token(db: Session) -> dict:
    settings = read_pricing_settings(db)
    missing = _missing_connection_fields(settings)
    if missing:
        raise ValueError(f"Missing eBay OAuth settings: {', '.join(missing)}")
    refresh_token = str(settings.get("ebay_refresh_token") or "").strip()
    if not refresh_token:
        raise ValueError("Missing eBay refresh token; reconnect the eBay account first")

    token_payload = _request_ebay_token(
        settings,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": " ".join(DEFAULT_EBAY_SCOPES),
        },
    )
    access_expires_at = _expires_at(token_payload.get("expires_in"))
    updates: dict[str, float | bool | str | None] = {
        "ebay_access_token": str(token_payload.get("access_token") or ""),
        "ebay_token_expires_at": access_expires_at,
    }
    returned_refresh_token = str(token_payload.get("refresh_token") or "")
    if returned_refresh_token:
        updates["ebay_refresh_token"] = returned_refresh_token
    refresh_expires_at = _expires_at(token_payload.get("refresh_token_expires_in")) or str(settings.get("ebay_refresh_token_expires_at") or "")
    if refresh_expires_at:
        updates["ebay_refresh_token_expires_at"] = refresh_expires_at
    write_pricing_settings(db, updates)
    env = ebay_environment_config(str(settings.get("ebay_environment", "sandbox")))
    return {
        "environment": env.name,
        "connected": True,
        "token_type": str(token_payload.get("token_type") or "User Access Token"),
        "access_token_expires_at": access_expires_at,
        "refresh_token_expires_at": refresh_expires_at or None,
        "scopes": DEFAULT_EBAY_SCOPES,
    }


def publish_ebay_sandbox_listing(db: Session, product_id: int) -> dict:
    settings = read_pricing_settings(db)
    env = ebay_environment_config(str(settings.get("ebay_environment", "sandbox")))
    if env.name != "sandbox":
        raise ValueError("Sandbox publish is only allowed when ebay_environment is sandbox")
    if not bool(settings.get("ebay_enable_writes", False)):
        raise ValueError("eBay writes are disabled; set ebay_enable_writes=true only after sandbox settings are ready")
    access_token = str(settings.get("ebay_access_token") or "").strip()
    if not access_token:
        raise ValueError("Missing eBay access token; complete OAuth before publishing")

    product = db.query(Product).options(selectinload(Product.listing_drafts)).filter(Product.id == product_id).first()
    if product is None:
        raise ValueError("Product not found")
    readiness = build_listing_readiness(db, product_id)
    if readiness is None:
        raise ValueError("Product not found")
    if not readiness["api_ready"]:
        raise ValueError(f"Listing is not API-ready: {', '.join(readiness['missing_api'])}")
    api_payload = build_ebay_api_payload(db, product_id)
    if api_payload is None:
        raise ValueError("Product not found")

    headers = _inventory_headers(access_token)
    sku = str(api_payload["sku"])
    inventory_url = f"{env.api_base_url}/sell/inventory/v1/inventory_item/{quote(sku, safe='')}"
    inventory_response = _checked_inventory_call(
        httpx.put(
            inventory_url,
            json=api_payload["inventory_item_payload"],
            headers=headers,
            timeout=30,
        ),
        "create inventory item",
        allowed_statuses={200, 201, 204},
    )
    offer_response = _checked_inventory_call(
        httpx.post(
            f"{env.api_base_url}/sell/inventory/v1/offer",
            json=api_payload["offer_payload"],
            headers=headers,
            timeout=30,
        ),
        "create offer",
        allowed_statuses={200, 201},
    )
    offer_body = _response_json(offer_response)
    offer_id = str(offer_body.get("offerId") or "").strip()
    if not offer_id:
        raise ValueError("eBay create offer response did not include offerId")
    publish_response = _checked_inventory_call(
        httpx.post(
            f"{env.api_base_url}/sell/inventory/v1/offer/{quote(offer_id, safe='')}/publish",
            headers=headers,
            timeout=30,
        ),
        "publish offer",
        allowed_statuses={200, 201},
    )
    publish_body = _response_json(publish_response)
    listing_id = str(publish_body.get("listingId") or "").strip()
    if not listing_id:
        raise ValueError("eBay publish response did not include listingId")

    price = api_payload["offer_payload"]["pricingSummary"]["price"]["value"]
    listing = EbayListing(
        product_id=product_id,
        listing_id=listing_id[:128],
        account_id=env.name,
        environment=env.name,
        price=float(price),
        quantity=int(api_payload["offer_payload"]["availableQuantity"]),
        status="published",
    )
    if product.listing_drafts:
        product.listing_drafts[0].status = "published"
    db.add(listing)
    db.commit()
    db.refresh(listing)

    return {
        "product_id": product_id,
        "sku": sku,
        "environment": env.name,
        "inventory_item_status_code": inventory_response.status_code,
        "offer_status_code": offer_response.status_code,
        "publish_status_code": publish_response.status_code,
        "offer_id": offer_id,
        "listing_id": listing_id,
        "listing_status": listing.status,
        "warnings": _response_warnings(offer_body) + _response_warnings(publish_body),
    }


def build_ebay_authorization_url(settings: dict[str, float | bool | str], state: str) -> str:
    env = ebay_environment_config(str(settings.get("ebay_environment", "sandbox")))
    params = {
        "client_id": str(settings.get("ebay_client_id") or ""),
        "redirect_uri": str(settings.get("ebay_redirect_uri") or ""),
        "response_type": "code",
        "scope": " ".join(DEFAULT_EBAY_SCOPES),
        "state": state,
    }
    return f"{env.auth_base_url}?{urlencode(params)}"


def _request_ebay_token(settings: dict[str, float | bool | str], data: dict[str, str]) -> dict:
    env = ebay_environment_config(str(settings.get("ebay_environment", "sandbox")))
    credentials = f"{settings.get('ebay_client_id') or ''}:{settings.get('ebay_client_secret') or ''}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    response = httpx.post(
        env.token_url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}",
        },
        timeout=20,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _token_error_detail(response)
        raise ValueError(f"eBay token request failed: {detail}") from exc
    payload = response.json()
    if not payload.get("access_token"):
        raise ValueError("eBay token response did not include an access token")
    return payload


def _inventory_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Content-Language": "en-US",
    }


def _checked_inventory_call(response: httpx.Response, action: str, allowed_statuses: set[int]) -> httpx.Response:
    if response.status_code in allowed_statuses:
        return response
    detail = _token_error_detail(response)
    raise ValueError(f"eBay {action} failed: {detail}")


def _response_json(response: httpx.Response) -> dict:
    if not response.content:
        return {}
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _response_warnings(payload: dict) -> list[str]:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return []
    messages: list[str] = []
    for warning in warnings:
        if isinstance(warning, dict):
            message = warning.get("message") or warning.get("longMessage") or warning.get("errorId")
            if message:
                messages.append(str(message))
    return messages


def _expires_at(seconds: object) -> str:
    try:
        value = int(seconds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        return ""
    return (datetime.now(UTC) + timedelta(seconds=value)).isoformat()


def _token_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    return str(payload.get("error_description") or payload.get("error") or payload)[:500]


def _missing_connection_fields(settings: dict[str, float | bool | str]) -> list[str]:
    required = {
        "ebay_client_id": "eBay Client ID",
        "ebay_client_secret": "eBay Client Secret",
        "ebay_redirect_uri": "eBay RuName / Redirect URI",
    }
    return [label for key, label in required.items() if not str(settings.get(key) or "").strip()]

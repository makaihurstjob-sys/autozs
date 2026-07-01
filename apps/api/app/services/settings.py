from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.domain import AppSetting


DEFAULT_SETTING_KEYS = {
    "default_ebay_fee_rate",
    "default_promoted_rate",
    "default_return_risk_rate",
    "default_undercut_amount",
    "default_min_profit",
    "default_min_profit_guard_enabled",
    "default_gift_card_discount_enabled",
    "default_gift_card_discount_percent",
    "default_risk_buffer",
    "default_margin_percent",
    "source_refresh_interval_days",
    "source_refresh_interval_hours",
    "default_pricing_strategy",
    "default_round_to_99",
    "default_rounding_cents",
    "default_offers_enabled",
    "default_listing_schedule_mode",
    "default_listing_schedule_days_ahead",
    "default_listing_schedule_time",
    "auto_delist_zero_view_enabled",
    "auto_delist_zero_view_days",
    "default_vero_remove_brand_from_title",
    "default_strip_brand_from_title",
    "default_title_suffix",
    "default_item_condition",
    "default_shipping_cost_type",
    "default_domestic_shipping_service",
    "default_buyer_shipping_cost",
    "ebay_environment",
    "ebay_marketplace_id",
    "ebay_client_id",
    "ebay_client_secret",
    "ebay_redirect_uri",
    "ebay_refresh_token",
    "ebay_refresh_token_expires_at",
    "ebay_access_token",
    "ebay_token_expires_at",
    "ebay_oauth_state",
    "ebay_enable_writes",
    "ebay_category_id",
    "ebay_merchant_location_key",
    "ebay_fulfillment_policy_id",
    "ebay_payment_policy_id",
    "ebay_return_policy_id",
    "ebay_expected_username",
    "ui_theme",
    "supplier_settings_json",
    "description_template_enabled",
    "description_template_name",
    "description_template_brand",
    "description_template_about",
    "description_template_shipping",
    "description_template_returns",
    "description_template_satisfaction",
    "keyword_blacklist_json",
    "buyer_accounts_json",
    "marketing_settings_json",
    "notifications_order_updates",
    "notifications_listing_errors",
    "notifications_email",
}

FLOAT_SETTING_KEYS = {
    "default_ebay_fee_rate",
    "default_promoted_rate",
    "default_return_risk_rate",
    "default_undercut_amount",
    "default_min_profit",
    "default_gift_card_discount_percent",
    "default_risk_buffer",
    "default_margin_percent",
    "source_refresh_interval_days",
    "source_refresh_interval_hours",
    "default_listing_schedule_days_ahead",
    "default_buyer_shipping_cost",
    "default_rounding_cents",
    "auto_delist_zero_view_days",
}


def read_pricing_settings(db: Session) -> dict[str, float | bool | str]:
    config = get_settings()
    values: dict[str, float | bool | str] = {
        "ebay_environment": config.ebay_environment,
        "ebay_enable_writes": config.ebay_enable_writes,
        "default_ebay_fee_rate": config.default_ebay_fee_rate,
        "default_promoted_rate": config.default_promoted_rate,
        "default_return_risk_rate": config.default_return_risk_rate,
        "default_undercut_amount": config.default_undercut_amount,
        "default_min_profit": config.default_min_profit,
        "default_min_profit_guard_enabled": False,
        "default_gift_card_discount_enabled": False,
        "default_gift_card_discount_percent": 6.0,
        "default_risk_buffer": config.default_risk_buffer,
        "default_margin_percent": 0.20,
        "source_refresh_interval_days": 7.0,
        "source_refresh_interval_hours": 6.0,
        "default_pricing_strategy": "margin",
        "default_round_to_99": False,
        "default_rounding_cents": 0.99,
        "default_offers_enabled": False,
        "default_listing_schedule_mode": "now",
        "default_listing_schedule_days_ahead": 0.0,
        "default_listing_schedule_time": "09:00",
        "auto_delist_zero_view_enabled": False,
        "auto_delist_zero_view_days": 25.0,
        "default_vero_remove_brand_from_title": True,
        "default_strip_brand_from_title": True,
        "default_title_suffix": " | FREE SHIPPING",
        "default_item_condition": "New",
        "default_shipping_cost_type": "flat",
        "default_domestic_shipping_service": "Economy Shipping",
        "default_buyer_shipping_cost": 0.0,
        "ebay_marketplace_id": "EBAY_US",
        "ebay_client_id": config.ebay_client_id,
        "ebay_client_secret": config.ebay_client_secret,
        "ebay_redirect_uri": config.ebay_redirect_uri,
        "ebay_refresh_token": config.ebay_refresh_token,
        "ebay_refresh_token_expires_at": config.ebay_refresh_token_expires_at,
        "ebay_access_token": config.ebay_access_token,
        "ebay_token_expires_at": config.ebay_token_expires_at,
        "ebay_oauth_state": "",
        "ebay_category_id": "",
        "ebay_merchant_location_key": "",
        "ebay_fulfillment_policy_id": "",
        "ebay_payment_policy_id": "",
        "ebay_return_policy_id": "",
        "ebay_expected_username": "",
        "ui_theme": "system",
        "supplier_settings_json": (
            '{"home_depot":{"enabled":true,"default_quantity":1,"country":"United States",'
            '"zipcode":"","shipping_method":"Cheapest with tracking"}}'
        ),
        "description_template_enabled": True,
        "description_template_name": "AutoZS Home Improvement",
        "description_template_brand": "AutoZS",
        "description_template_about": (
            "We source useful home improvement products and prepare every listing with clear product details, "
            "reliable service, and responsive support."
        ),
        "description_template_shipping": (
            "Orders are processed promptly and shipped to the address provided at checkout. Delivery estimates "
            "can vary by destination, carrier conditions, weather, and supplier availability."
        ),
        "description_template_returns": (
            "Returns are accepted according to the return policy shown on this listing. Items should be returned "
            "in the same condition received unless the item arrived damaged or incorrect."
        ),
        "description_template_satisfaction": (
            "If there is a problem with your order, message us through eBay so we can help make it right."
        ),
        "keyword_blacklist_json": "[]",
        "buyer_accounts_json": "[]",
        "marketing_settings_json": '{"global":{"enabled":true,"promoted_rate":0.02,"campaign_strategy":"balanced","daily_budget":5.0,"apply_to_all":true},"accounts":{}}',
        "notifications_order_updates": True,
        "notifications_listing_errors": True,
        "notifications_email": "",
    }
    stored_keys: set[str] = set()
    for setting in db.query(AppSetting).all():
        stored_keys.add(setting.key)
        if setting.key in FLOAT_SETTING_KEYS:
            values[setting.key] = float(setting.value)
        elif setting.key in {
            "default_round_to_99",
            "default_min_profit_guard_enabled",
            "default_gift_card_discount_enabled",
            "default_offers_enabled",
            "auto_delist_zero_view_enabled",
            "default_vero_remove_brand_from_title",
            "default_strip_brand_from_title",
            "ebay_enable_writes",
            "description_template_enabled",
            "notifications_order_updates",
            "notifications_listing_errors",
        }:
            values[setting.key] = setting.value.lower() == "true"
        elif setting.key in DEFAULT_SETTING_KEYS:
            values[setting.key] = setting.value
    if "source_refresh_interval_days" in stored_keys and "source_refresh_interval_hours" not in stored_keys:
        values["source_refresh_interval_hours"] = float(values["source_refresh_interval_days"]) * 24
    values["default_strip_brand_from_title"] = bool(values.get("default_vero_remove_brand_from_title", values["default_strip_brand_from_title"]))
    return values


def write_pricing_settings(db: Session, updates: dict[str, float | bool | str | None]) -> dict[str, float | bool | str]:
    updates = dict(updates)
    if updates.get("source_refresh_interval_days") is not None and updates.get("source_refresh_interval_hours") is None:
        updates["source_refresh_interval_hours"] = float(updates["source_refresh_interval_days"]) * 24
    for key, value in updates.items():
        if key not in DEFAULT_SETTING_KEYS or value is None:
            continue
        if key == "default_pricing_strategy" and value not in {"margin", "competitor", "safe_competitor"}:
            continue
        if key == "default_listing_schedule_mode" and value not in {"now", "scheduled"}:
            continue
        if key == "default_shipping_cost_type" and value not in {"flat", "calculated"}:
            continue
        if key == "ui_theme" and value not in {"system", "light", "dark"}:
            continue
        if key == "ebay_environment" and value not in {"sandbox", "production"}:
            continue
        if key == "ebay_enable_writes" and isinstance(value, str):
            value = value.lower() == "true"
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting is None:
            setting = AppSetting(key=key, value=str(value))
            db.add(setting)
        else:
            setting.value = str(value)
    db.commit()
    return read_pricing_settings(db)

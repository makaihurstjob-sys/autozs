from functools import lru_cache
import platform
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    app_name: str = "eBay Automation MVP"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'dev.db'}"
    redis_url: str = "redis://redis:6379/0"
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str = r"https?://.*"
    ebay_environment: str = "sandbox"
    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    ebay_redirect_uri: str = ""
    ebay_refresh_token: str = ""
    ebay_refresh_token_expires_at: str = ""
    ebay_access_token: str = ""
    ebay_token_expires_at: str = ""
    ebay_enable_writes: bool = False
    default_ebay_fee_rate: float = 0.1325
    default_promoted_rate: float = 0.0
    default_return_risk_rate: float = 0.02
    default_undercut_amount: float = 0.20
    default_min_profit: float = 8.00
    default_risk_buffer: float = 3.00
    catalog_automation_interval_minutes: int = 360
    ebay_report_watch_enabled: bool = True
    ebay_report_watch_interval_seconds: float = 2.0
    ebay_report_inbox: str = ""
    autozs_worker_id: str = "local-worker"
    autozs_worker_label: str = platform.node() or "Local Worker"
    autozs_worker_role: str = "operations"
    autozs_chrome_executable_path: str = ""
    autozs_chrome_profile_root: str = ""
    autozs_ebay_profile_root: str = ""
    autozs_home_depot_profile_root: str = ""
    autozs_push_vapid_public_key: str = ""
    autozs_push_vapid_private_key: str = ""
    autozs_push_vapid_subject: str = "mailto:alerts@autozs.local"
    autozs_push_alert_loop_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

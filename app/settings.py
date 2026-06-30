from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./storage/excisewatch.db"
    source_config_path: str = "./data/sources.yaml"
    snapshot_dir: str = "./storage/snapshots"
    doc_dir: str = "./storage/docs"
    http_timeout_seconds: int = 25
    user_agent: str = "ExciseWatchBot/0.1 compliance-monitoring"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    slack_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_parse_mode: str | None = None
    telegram_disable_web_page_preview: bool = True
    telegram_digest_limit: int = 25
    telegram_include_chatter_by_default: bool = False
    telegram_min_tier: str = "REPORTED_NOT_CONFIRMED"
    email_smtp_host: str | None = None
    email_smtp_port: int = 587
    email_smtp_user: str | None = None
    email_smtp_password: str | None = None
    email_to: str | None = None
    jwt_secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 720
    scheduler_enabled: bool = False
    review_required_for_official: bool = True
    auto_alert_official: bool = False
    chatter_private_only: bool = True
    source_live_fetch_default: bool = False
    source_validation_max_sources: int = 200
    compliance_min_official_sources: int = 1

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

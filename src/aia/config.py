"""Typed application settings.

Everything is read from environment variables (12-factor) with sane local-first
defaults. The onboarding wizard writes most of these into `.env`. Never hardcode
secrets — see `aia.security` for how credentials are encrypted at rest.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- Core ----
    env: Literal["local", "hosted"] = Field("local", alias="AIA_ENV")
    tenant_id: str = Field("default", alias="AIA_TENANT_ID")
    log_level: str = Field("INFO", alias="AIA_LOG_LEVEL")

    # ---- Secrets ----
    # Optional explicit master key (headless installs). On a laptop it is kept in
    # the OS keychain and loaded by aia.security.keyring_master instead.
    master_key: str | None = Field(None, alias="AIA_MASTER_KEY")

    # ---- Datastore ----
    database_url: str = Field(
        "postgresql+asyncpg://aia:aia@localhost:5432/aia", alias="DATABASE_URL"
    )
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")

    # ---- LLM (hybrid) ----
    ollama_base_url: str = Field("http://localhost:11434", alias="OLLAMA_BASE_URL")
    llm_local_model: str = Field(
        "ollama/llama3.1:8b-instruct-q4_K_M", alias="LLM_LOCAL_MODEL"
    )
    llm_cloud_model: str = Field("openai/gpt-4o-mini", alias="LLM_CLOUD_MODEL")
    llm_embedding_model: str = Field("ollama/nomic-embed-text", alias="LLM_EMBEDDING_MODEL")
    llm_force_cloud: bool = Field(False, alias="LLM_FORCE_CLOUD")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")

    # ---- WhatsApp ----
    whatsapp_provider: Literal["baileys", "cloud"] = Field("baileys", alias="WHATSAPP_PROVIDER")
    whatsapp_gateway_url: str = Field("http://localhost:8085", alias="WHATSAPP_GATEWAY_URL")
    whatsapp_cloud_token: str | None = Field(None, alias="WHATSAPP_CLOUD_TOKEN")
    whatsapp_cloud_phone_id: str | None = Field(None, alias="WHATSAPP_CLOUD_PHONE_ID")

    # ---- OAuth client apps ----
    google_client_id: str | None = Field(None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(None, alias="GOOGLE_CLIENT_SECRET")
    ms_client_id: str | None = Field(None, alias="MS_CLIENT_ID")
    ms_client_secret: str | None = Field(None, alias="MS_CLIENT_SECRET")
    ms_tenant: str = Field("common", alias="MS_TENANT")

    # ---- Voice ----
    twilio_account_sid: str | None = Field(None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(None, alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str | None = Field(None, alias="TWILIO_PHONE_NUMBER")
    deepgram_api_key: str | None = Field(None, alias="DEEPGRAM_API_KEY")

    # ---- Nutrition ----
    nutrition_provider: Literal["usda", "nutritionix", "openfoodfacts"] = Field(
        "usda", alias="NUTRITION_PROVIDER"
    )
    usda_api_key: str | None = Field(None, alias="USDA_API_KEY")
    nutritionix_app_id: str | None = Field(None, alias="NUTRITIONIX_APP_ID")
    nutritionix_api_key: str | None = Field(None, alias="NUTRITIONIX_API_KEY")

    # ---- Tasks ----
    tasks_provider: Literal["local", "notion", "todoist", "google_tasks"] = Field(
        "local", alias="TASKS_PROVIDER"
    )
    notion_token: str | None = Field(None, alias="NOTION_TOKEN")
    todoist_token: str | None = Field(None, alias="TODOIST_TOKEN")

    # ---- Onboarding ----
    onboarding_port: int = Field(8088, alias="ONBOARDING_PORT")
    public_base_url: str = Field("http://localhost:8088", alias="PUBLIC_BASE_URL")

    @property
    def offline(self) -> bool:
        """True when no cloud LLM key is configured -> run 100% locally."""
        return not (self.openai_api_key or self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    """Cached singleton. Import this everywhere instead of reading env directly."""
    return Settings()

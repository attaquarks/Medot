"""Typed runtime settings.

Only publishable credentials ever appear here (Supabase project URL +
anon/publishable key). Privileged keys are never configured — the service-role
key must not exist in this process (AC4). Values come from environment or the
non-secret config file written by the desktop installer.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEDOT_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    supabase_url: str = Field("", alias="MEDOT_SUPABASE_URL")
    supabase_publishable_key: str = Field("", alias="MEDOT_SUPABASE_PUBLISHABLE_KEY")
    # Loopback API for the desktop console.
    api_host: str = Field("127.0.0.1", alias="MEDOT_API_HOST")
    api_port: int = Field(8756, alias="MEDOT_API_PORT")
    # OAuth deep link registered by the desktop shell.
    auth_redirect_uri: str = Field("medot://auth/callback", alias="MEDOT_AUTH_REDIRECT_URI")
    # Overrides the default workspace root (tests, portable installs).
    data_dir: str | None = Field(None, alias="MEDOT_DATA_DIR")

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()

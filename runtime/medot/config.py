"""Typed runtime settings.

Only publishable credentials ever appear here (Supabase project URL +
anon/publishable key). Privileged keys are never configured — the service-role
key must not exist in this process (AC4).

Resolution order for the Supabase values:
  1. environment variables (dev),
  2. a `config.toml` bundled beside the code (`--add-data` at PyInstaller
     build time — CI writes it from repository secrets; nothing is baked into
     source).
"""
from __future__ import annotations

import os
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _apply_bundled_config() -> None:
    """Load `config.toml` (publishable values only) into the environment.

    Only sets variables the user did not already provide. When frozen, the
    file unpacks to sys._MEIPASS; in dev it sits next to the source root.
    """
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "config.toml")
        candidates.append(Path(sys.executable).parent / "config.toml")
    else:
        candidates.append(Path(__file__).resolve().parent.parent / "config.toml")

    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        mapping = {
            "supabase_url": "MEDOT_SUPABASE_URL",
            "publishable_key": "MEDOT_SUPABASE_PUBLISHABLE_KEY",
        }
        for key, env_var in mapping.items():
            value = data.get("supabase", {}).get(key)
            if value and not os.environ.get(env_var):
                os.environ[env_var] = str(value)
        return


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
    _apply_bundled_config()
    return Settings()

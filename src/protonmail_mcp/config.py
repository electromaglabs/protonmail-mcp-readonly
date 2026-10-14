from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# <repo>/src/protonmail_mcp/config.py → <repo>/.env. Läses även när servern
# startas från en annan katalog (t.ex. uv run --project <repo>).
PROJECT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    imap_host: str = "127.0.0.1"
    imap_port: int = 1143
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1026
    username: str
    password: str
    verify_ssl: bool = False
    smtp_ca_cert: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="PROTONMAIL_",
        # Senare filer vinner: en .env i arbetskatalogen går före projektrotens
        env_file=(PROJECT_ENV_FILE, ".env"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

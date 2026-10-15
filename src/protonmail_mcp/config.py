from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# <repo>/src/protonmail_mcp/config.py → <repo>/.env. Läses även när servern
# startas från en annan katalog (t.ex. uv run --project <repo>).
PROJECT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    imap_host: str = "127.0.0.1"
    imap_port: int = 1143
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1026
    # Sekunder per IMAP-kommando. aioimaplib har 10 s som standard, men en
    # SEARCH i All Mail tar 5–9 s mot Bridge på ett konto med ~30 000 mejl.
    imap_timeout: float = Field(default=30.0, gt=0)
    username: str
    password: str
    verify_ssl: bool = False
    smtp_ca_cert: str | None = None
    # All filåtkomst för bilagor (get_attachment, attachments-parametern)
    # begränsas till den här katalogen. Den skapas med rättigheterna 0700
    # när servern startar. Måste vara absolut (eller börja med ~): Claude
    # Desktop startar ofta servern med arbetskatalogen /.
    attachment_dir: Path = Field(default=Path("~/Downloads/protonmail-mcp"), validate_default=True)
    # Största bilaga som get_attachment returnerar direkt (save=False), i byte
    attachment_max_inline_bytes: int = Field(default=1024 * 1024, gt=0)

    # --- Begränsningar av vad servern (och därmed en LLM) får göra ---
    # Kontrolleras centralt (policy.py): i IMAP-klientens skrivfunktioner,
    # i SMTP-klientens leverans och i MCP-servern före varje verktyg.
    # Alla vägringar är fel som når klienten; inget skickas till Bridge.
    #
    # PROTONMAIL_READ_ONLY=true: allt som ändrar kontot vägras — flytt,
    # radering, läst/oläst, stjärna, etiketter, mappar, utkast och skick.
    # Läsande verktyg fungerar som vanligt. Standard: false.
    read_only: bool = False
    # PROTONMAIL_SEND_MODE:
    #   "send" (standard) — som tidigare: verktygen får skicka.
    #   "draft_only" — send_email, reply_to_email, forward_email och send_draft
    #       vägras; utkast (create_draft, create_reply_draft,
    #       create_forward_draft, update_draft) går bra, så att användaren
    #       själv granskar och skickar från Proton.
    #   "disabled" — även utkasten vägras.
    send_mode: Literal["send", "draft_only", "disabled"] = "send"

    model_config = SettingsConfigDict(
        env_prefix="PROTONMAIL_",
        # Senare filer vinner: en .env i arbetskatalogen går före projektrotens
        env_file=(PROJECT_ENV_FILE, ".env"),
        # Annars skriver pydantic input_value={'password': ...} i felet,
        # och lifespan loggar det till stderr (som Claude Desktop sparar).
        hide_input_in_errors=True,
    )

    @field_validator("send_mode", mode="before")
    @classmethod
    def _normalize_send_mode(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("attachment_dir", mode="after")
    @classmethod
    def _expand_home(cls, value: Path) -> Path:
        value = value.expanduser()
        if not value.is_absolute():
            raise ValueError(
                "PROTONMAIL_ATTACHMENT_DIR måste vara en absolut sökväg (eller börja med ~)"
            )
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

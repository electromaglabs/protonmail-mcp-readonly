from __future__ import annotations

import ipaddress
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for the read-only fork.

    There are no SMTP settings: this fork cannot send mail. Old PROTONMAIL_SMTP_*
    and PROTONMAIL_VERIFY_SSL values are ignored if they are still set.
    """

    imap_host: str = "127.0.0.1"
    imap_port: int = 1143
    username: str
    password: str
    # Optional comma-separated list of mailboxes Claude may read, for example
    # "Labels/Claude" or "INBOX,Folders/Receipts". Unset or empty = all mailboxes.
    allowed_mailboxes: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="PROTONMAIL_",
        env_file=".env",
        extra="ignore",
    )

    @field_validator("imap_host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        # The IMAP connection to Bridge is unencrypted, so the Bridge password
        # and all mail would cross the network in clear text on any other host.
        if value.lower() == "localhost":
            return value
        try:
            if ipaddress.ip_address(value).is_loopback:
                return value
        except ValueError:
            pass
        raise ValueError(
            "imap_host must be this computer (127.0.0.1, ::1 or localhost); "
            "the connection to Bridge is not encrypted"
        )

    @property
    def allowed_mailbox_set(self) -> frozenset[str] | None:
        """The allow-list as a set, or None when every mailbox is allowed."""
        if not self.allowed_mailboxes:
            return None
        names = {n.strip() for n in self.allowed_mailboxes.split(",") if n.strip()}
        return frozenset(names) or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

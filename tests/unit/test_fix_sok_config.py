"""Enhetstester: PROTONMAIL_IMAP_TIMEOUT (fix-sok, N8)."""
import pytest
from pydantic import ValidationError

from protonmail_mcp.config import Settings


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    monkeypatch.delenv("PROTONMAIL_IMAP_TIMEOUT", raising=False)


def test_default_is_30_seconds():
    assert Settings(_env_file=None).imap_timeout == 30.0


def test_accepts_fractional_seconds(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_IMAP_TIMEOUT", "45.5")
    assert Settings(_env_file=None).imap_timeout == 45.5


@pytest.mark.parametrize("bad", ["0", "-5", "abc"])
def test_rejects_non_positive_or_garbage(monkeypatch, bad):
    monkeypatch.setenv("PROTONMAIL_IMAP_TIMEOUT", bad)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_client_uses_configured_timeout(monkeypatch):
    from protonmail_mcp.imap_client import IMAPClient
    monkeypatch.setenv("PROTONMAIL_IMAP_TIMEOUT", "45")
    client = IMAPClient(Settings(_env_file=None))
    assert (client.timeout, client.uid_timeout) == (45, 45)


def test_client_default_timeout_is_30(monkeypatch):
    from protonmail_mcp.imap_client import IMAPClient
    client = IMAPClient(Settings(_env_file=None))
    assert (client.timeout, client.uid_timeout) == (30, 30)

"""Enhetstester: SEARCH/FETCH som inte svarar OK ger ValueError med serverns text (fix-sok, N5)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from protonmail_mcp.imap_client import IMAPClient
from tests.fix_sok_fakebox import imap_mock


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    imap = IMAPClient(Settings(_env_file=None))
    imap._client = imap_mock()
    return imap


@pytest.mark.parametrize("result", ["NO", "BAD"])
async def test_search_not_ok_raises_with_server_text(client, result):
    client._client.search = AsyncMock(return_value=SimpleNamespace(
        result=result, lines=[b"[Error offset=35]: expected - after year"]))
    with pytest.raises(ValueError, match=r"Sökningen misslyckades.*expected - after year"):
        await client.search_messages("INBOX", unseen=True)


async def test_fetch_not_ok_raises_with_server_text(client):
    client._client.search = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"1 2"]))
    client._client.fetch = AsyncMock(return_value=SimpleNamespace(result="NO", lines=[b"fetch failed"]))
    with pytest.raises(ValueError, match=r"Hämtningen av sökträffarna misslyckades.*fetch failed"):
        await client.search_messages("INBOX")


async def test_error_without_text_still_names_result(client):
    client._client.search = AsyncMock(return_value=SimpleNamespace(result="NO", lines=[]))
    with pytest.raises(ValueError, match=r"\(NO\)"):
        await client.search_messages("INBOX")

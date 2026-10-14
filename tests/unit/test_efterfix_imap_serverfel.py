"""NO/BAD från Bridge på LIST och FETCH ska bli fel med serverns text (F3/K3).

Förut gav LIST NO en tom lista, FETCH NO i list_messages en tom sida och
UID FETCH NO i get_message/get_message_headers None ("inget meddelande").
None betyder nu bara att svaret var OK men saknade meddelandet.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.fix_sok_fakebox import imap_mock


def _no(text="backend unavailable", result="NO"):
    return SimpleNamespace(result=result, lines=[text.encode()])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    from protonmail_mcp.imap_client import IMAPClient
    imap = IMAPClient(Settings(_env_file=None))
    imap._client = imap_mock()
    imap._client.select.return_value = SimpleNamespace(result="OK", lines=[b"5 EXISTS"])
    return imap


@pytest.mark.parametrize("result", ["NO", "BAD"])
async def test_list_mailboxes_raises_on_refusal(client, result):
    client._client.list = AsyncMock(return_value=_no("sync in progress", result))
    with pytest.raises(ValueError, match=f"{result}.*sync in progress"):
        await client.list_mailboxes()


async def test_list_messages_raises_when_fetch_refused(client):
    client._client.fetch = AsyncMock(return_value=_no())
    with pytest.raises(ValueError, match="INBOX.*NO.*backend unavailable"):
        await client.list_messages("INBOX")


async def test_get_message_raises_when_fetch_refused(client):
    client._client.uid = AsyncMock(return_value=_no("failed to build message"))
    with pytest.raises(ValueError, match="UID 4.*INBOX.*NO.*failed to build message"):
        await client.get_message("INBOX", "4")


async def test_get_message_headers_raises_when_fetch_refused(client):
    client._client.uid = AsyncMock(return_value=_no("failed to build message"))
    with pytest.raises(ValueError, match="UID 4.*INBOX.*NO.*failed to build message"):
        await client.get_message_headers("INBOX", "4")


async def test_get_message_ok_without_literal_is_still_none(client):
    client._client.uid = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"UID FETCH completed"]))
    assert await client.get_message("INBOX", "4") is None
    assert await client.get_message_headers("INBOX", "4") is None

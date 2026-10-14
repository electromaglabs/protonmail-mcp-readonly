"""Enhetstester för IMAP-anslutningens livscykel: SELECT, LOGIN, timeouter och återanslutning."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient

OK = SimpleNamespace(result="OK", lines=[])


def _mock_imap(state: str = "SELECTED") -> AsyncMock:
    """En aioimaplib.IMAP4-attrapp: asynkrona kommandon, synkrona get_state/transport."""
    m = AsyncMock()
    m.select.return_value = OK
    m.get_state = MagicMock(return_value=state)
    m.protocol = MagicMock()
    return m


@pytest.fixture
def settings():
    return Settings(username="u@example.com", password="pw", _env_file=None)


@pytest.fixture
def client(settings):
    imap = IMAPClient(settings)
    imap._client = _mock_imap()
    return imap


SELECTING_CALLS = [
    ("list_messages", ("Finns-inte",)),
    ("get_message", ("Finns-inte", "1")),
    ("search_messages", ("Finns-inte",)),
    ("set_flags", ("Finns-inte", "1", r"(\Seen)", True)),
    ("move_message", ("Finns-inte", "1", "Archive")),
    ("delete_message", ("Finns-inte", "1")),
    ("get_message_headers", ("Finns-inte", "1")),
]


# ---------------------------------------------------------------------------
# K6: SELECT-svaret måste kontrolleras
# ---------------------------------------------------------------------------
class TestSelectChecked:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,args", SELECTING_CALLS)
    async def test_failed_select_raises_and_sends_nothing_more(self, client, method, args):
        imap = client._client
        imap.select.return_value = SimpleNamespace(result="NO", lines=[b"no such mailbox"])

        with pytest.raises(ValueError, match="Mappen finns inte.*Finns-inte"):
            await getattr(client, method)(*args)

        imap.uid.assert_not_called()
        imap.fetch.assert_not_called()
        imap.search.assert_not_called()
        imap.expunge.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_select_discards_connection(self, client):
        """Bridge står kvar i förra mappen efter NO; anslutningen får inte återanvändas."""
        imap = client._client
        imap.select.return_value = SimpleNamespace(result="NO", lines=[b"no such mailbox"])

        with pytest.raises(ValueError):
            await client.delete_message("Finns-inte", "1")

        assert client._client is None
        imap.protocol.transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_select_keeps_connection(self, client):
        imap = client._client
        await client.delete_message("INBOX", "1")
        assert client._client is imap
        imap.select.assert_awaited_once_with('"INBOX"')

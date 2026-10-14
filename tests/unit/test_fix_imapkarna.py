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


# ---------------------------------------------------------------------------
# lifecycle-nonauth: en misslyckad inloggning får inte låsa klienten
# ---------------------------------------------------------------------------
class TestLoginLifecycle:
    @pytest.fixture
    def fresh(self, settings):
        return IMAPClient(settings)

    @pytest.mark.asyncio
    async def test_login_no_raises_and_leaves_no_client(self, fresh):
        new = _mock_imap(state="NONAUTH")
        new.login.return_value = SimpleNamespace(result="NO", lines=[b"[AUTHENTICATIONFAILED] no such user"])
        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=new):
            with pytest.raises(Exception, match="Inloggningen.*misslyckades"):
                await fresh.connect()
        assert fresh._client is None
        new.protocol.transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelled_login_leaves_no_client(self, fresh):
        new = _mock_imap(state="NONAUTH")
        new.login.side_effect = asyncio.CancelledError
        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=new):
            with pytest.raises(asyncio.CancelledError):
                await fresh.connect()
        assert fresh._client is None
        new.protocol.transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_timeout_has_message_and_leaves_no_client(self, fresh):
        new = _mock_imap(state="NONAUTH")
        new.login.side_effect = asyncio.TimeoutError
        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=new):
            with pytest.raises((asyncio.TimeoutError, TimeoutError), match="inloggning"):
                await fresh.connect()
        assert fresh._client is None

    @pytest.mark.asyncio
    async def test_successful_login_sets_client(self, fresh):
        new = _mock_imap(state="AUTH")
        new.login.return_value = OK
        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=new):
            await fresh.connect()
        assert fresh._client is new

    @pytest.mark.asyncio
    async def test_ensure_connected_replaces_unauthenticated_client(self, client):
        """NOOP är tillåtet i NONAUTH, så NOOP ensam kan inte avgöra att klienten är frisk."""
        old = _mock_imap(state="NONAUTH")
        client._client = old
        new = _mock_imap(state="AUTH")
        new.login.return_value = OK
        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=new):
            await client._ensure_connected()
        assert client._client is new
        old.protocol.transport.close.assert_called_once()


# ---------------------------------------------------------------------------
# uid-no-timeout: UID STORE/COPY/EXPUNGE får inte hänga med låset taget
# ---------------------------------------------------------------------------
async def _never_answers(*_args, **_kwargs):
    await asyncio.Event().wait()


UID_WRITING_CALLS = [
    ("set_flags", ("INBOX", "1", r"(\Seen)", True)),
    ("move_message", ("INBOX", "1", "Archive")),
    ("delete_message", ("INBOX", "1")),
]


class TestUidTimeout:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,args", UID_WRITING_CALLS)
    async def test_hanging_uid_command_times_out_and_discards_connection(self, client, method, args):
        imap = client._client
        imap.uid.side_effect = _never_answers
        client.uid_timeout = 0.05

        with pytest.raises((asyncio.TimeoutError, TimeoutError), match="UID"):
            await asyncio.wait_for(getattr(client, method)(*args), 2)

        assert not client._lock.locked()
        assert client._client is None
        imap.protocol.transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelled_operation_discards_connection(self, client):
        """aioimaplib rensar inte hängande kommandon vid avbrott; anslutningen är då oanvändbar."""
        imap = client._client
        imap.uid.side_effect = _never_answers
        task = asyncio.ensure_future(client.set_flags("INBOX", "1", r"(\Seen)", True))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert client._client is None
        imap.protocol.transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_validation_error_keeps_connection(self, client):
        imap = client._client
        with pytest.raises(ValueError):
            await client.delete_message("INBOX", "1:*")
        assert client._client is imap


# ---------------------------------------------------------------------------
# reconnect-leak: den gamla anslutningen ska stängas
# ---------------------------------------------------------------------------
class TestNoLeakedConnections:
    @pytest.mark.asyncio
    async def test_reconnect_after_failed_noop_closes_old_transport(self, client):
        old = client._client
        old.noop.side_effect = ConnectionResetError
        new = _mock_imap(state="AUTH")
        new.login.return_value = OK
        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=new):
            await client._ensure_connected()
        assert client._client is new
        old.protocol.transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_closes_transport_when_logout_fails(self, client):
        old = client._client
        old.logout.side_effect = asyncio.TimeoutError
        await client.disconnect()
        assert client._client is None
        old.protocol.transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_closes_transport_after_logout(self, client):
        old = client._client
        await client.disconnect()
        old.logout.assert_awaited_once()
        old.protocol.transport.close.assert_called_once()

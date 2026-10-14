"""Avbruten anslutning: pågående och senare kommandon avbryts direkt (K4).

Förut släppte conn_lost_cb bara klienten. Ett kommando som väntade, eller
som skickades ut på den döda transporten, väntade ut hela timeouten och
gav aioimaplib:s råa CommandTimeout eller "svarade inte på UID STORE".
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import aioimaplib
import pytest

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient, _BridgeProtocol


def _protocol():
    protocol = _BridgeProtocol(asyncio.get_running_loop())
    protocol.transport = MagicMock()
    protocol.state = aioimaplib.SELECTED
    return protocol


async def test_pending_command_fails_at_once():
    protocol = _protocol()
    cmd = aioimaplib.Command("SEARCH", "A1", timeout=30)
    protocol.pending_sync_command = cmd
    protocol.connection_lost(ConnectionResetError("reset by peer"))
    with pytest.raises(ConnectionError, match="bröts.*SEARCH"):
        await asyncio.wait_for(cmd.wait(), 1)


async def test_pending_async_command_fails_at_once():
    protocol = _protocol()
    cmd = aioimaplib.Command("FETCH", "A2", timeout=30)
    protocol.pending_async_commands["FETCH"] = cmd
    protocol.connection_lost(None)
    with pytest.raises(ConnectionError, match="bröts"):
        await asyncio.wait_for(cmd.wait(), 1)


async def test_command_after_loss_fails_at_once():
    protocol = _protocol()
    protocol.connection_lost(None)
    cmd = aioimaplib.Command("NOOP", protocol.new_tag(), timeout=30)
    with pytest.raises(ConnectionError, match="bröts"):
        await asyncio.wait_for(protocol.execute(cmd), 1)
    protocol.transport.write.assert_not_called()


@pytest.fixture
def client(monkeypatch):
    return IMAPClient(Settings(username="u", password="p", _env_file=None))


def _fake_with_protocol(protocol):
    fake = MagicMock()
    fake.protocol = protocol

    async def noop():
        # NOOP "lyckas": bara kontrollen av den brutna anslutningen kan avslöja den
        return SimpleNamespace(result="OK", lines=[])

    fake.noop = noop
    return fake


async def test_lost_connection_is_replaced_before_next_call(client, monkeypatch):
    protocol = _protocol()
    protocol.connection_lost(None)
    client._client = _fake_with_protocol(protocol)
    connected = []

    async def fake_connect():
        connected.append(True)
        client._client = SimpleNamespace(protocol=SimpleNamespace(state="AUTH"))

    monkeypatch.setattr(client, "connect", fake_connect)
    await client._ensure_connected()
    assert connected == [True]


async def test_loss_during_a_call_keeps_client_until_call_ends(client):
    """conn_lost_cb mitt i ett anrop får inte ge AttributeError på self._client."""
    from unittest.mock import patch
    fake = MagicMock()
    fake.protocol = MagicMock(state="AUTH")

    async def ok(*a, **k):
        return SimpleNamespace(result="OK", lines=[])

    fake.wait_hello_from_server = ok
    fake.login = ok
    with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=fake) as ctor:
        await client.connect()
    conn_lost_cb = ctor.call_args.kwargs["conn_lost_cb"]
    async with client._lock:
        conn_lost_cb(ConnectionResetError())
        assert client._client is fake

"""Otaggade svarsrader: bara det inledande "* " ska tas bort (K2).

aioimaplib 2.0.1 gör line.replace(b'* ', b'') på hela raden, så
'* LIST (\\HasNoChildren) "/" "Folders/* Viktigt"' blev "Folders/Viktigt".
IMAPClient byter därför protokollklass på anslutningen.
"""
import aioimaplib
import pytest

from protonmail_mcp.imap_client import _BridgeProtocol, _use_bridge_protocol


def _feed(protocol, command, *lines):
    protocol.state = aioimaplib.SELECTED
    protocol.pending_sync_command = command
    protocol.data_received(b"".join(lines))
    return command.response.lines


async def test_inner_asterisk_space_is_kept():
    protocol = _BridgeProtocol(None)
    cmd = aioimaplib.Command("LIST", "A1")
    lines = _feed(protocol, cmd, b'* LIST (\\HasNoChildren) "/" "Folders/* Viktigt"\r\n',
                  b'* LIST () "/" "Labels/a* b"\r\n')
    assert lines == [b'LIST (\\HasNoChildren) "/" "Folders/* Viktigt"', b'LIST () "/" "Labels/a* b"']


async def test_untagged_fetch_and_exists_still_routed():
    protocol = _BridgeProtocol(None)
    cmd = aioimaplib.Command("SELECT", "A1")
    lines = _feed(protocol, cmd, b"* 3 EXISTS\r\n", b"* OK [UIDVALIDITY 1] x\r\n")
    assert lines == [b"3 EXISTS", b"OK [UIDVALIDITY 1] x"]


async def test_async_fetch_response_routed_to_fetch_command():
    protocol = _BridgeProtocol(None)
    protocol.state = aioimaplib.SELECTED
    cmd = aioimaplib.Command("FETCH", "A2")
    protocol.pending_async_commands["FETCH"] = cmd
    protocol.data_received(b'* 1 FETCH (UID 5 FLAGS (\\Seen))\r\n')
    assert cmd.response.lines == [b"1 FETCH (UID 5 FLAGS (\\Seen))"]


async def test_connection_gets_the_bridge_protocol():
    client = aioimaplib.IMAP4(host="127.0.0.1", port=9, timeout=1)
    _use_bridge_protocol(client)
    assert isinstance(client.protocol, _BridgeProtocol)
    client._client_task.cancel()


def test_mock_protocol_is_left_alone():
    from unittest.mock import MagicMock
    client = MagicMock()
    protocol = client.protocol
    _use_bridge_protocol(client)
    assert client.protocol is protocol

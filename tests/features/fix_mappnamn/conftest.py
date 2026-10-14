"""Gemensamma steg för mappnamnsscenarierna (fix-mappnamn).

Scenarierna kör de riktiga MCP-verktygen och den riktiga IMAPClient. Bara
aioimaplib-anslutningen är mockad, så det som kontrolleras är vad Bridge
skickar i LIST och vad Bridge får tillbaka i nästa kommando.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, parsers, then, when

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.tools.mailboxes import get_mailbox_status, list_mailboxes

# Innehållet i en IMAP quoted-string (RFC 3501): allt utom " och \, eller ett escapat tecken
_WIRE = r'(?P<wire>(?:[^"\\]|\\.)*)'


@pytest.fixture
def bridge(monkeypatch, mock_ctx):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    imap = IMAPClient(Settings())
    imap._client = AsyncMock()
    imap._client.noop.return_value = SimpleNamespace(result="OK", lines=[])
    imap._client.status.return_value = SimpleNamespace(
        result="OK", lines=['"x" (MESSAGES 0 UNSEEN 0)', "STATUS completed"]
    )
    lines: list[str] = []
    imap._client.list.side_effect = lambda *args: SimpleNamespace(
        result="OK", lines=[*lines, "LIST completed"]
    )
    mock_ctx.request_context.lifespan_context.imap = imap
    return SimpleNamespace(imap=imap, lines=lines, wire_names=[], errors=[])


def _add_list_line(bridge, wire: str, attrs: str) -> None:
    bridge.lines.append(f'({attrs}) "/" "{wire}"')
    bridge.wire_names.append(wire)


@given(parsers.re(rf'att Bridge listar mappen "{_WIRE}"$'))
def bridge_lists(bridge, wire):
    _add_list_line(bridge, wire, "\\Unmarked")


@given(parsers.re(rf'att Bridge listar mappen "{_WIRE}" med attributen "(?P<attrs>[^"]*)"$'))
def bridge_lists_with_attrs(bridge, wire, attrs):
    _add_list_line(bridge, wire, attrs)


@when("jag listar mapparna", target_fixture="mappar")
def list_folders(mock_ctx, bridge):
    return asyncio.run(list_mailboxes(mock_ctx))


@when(parsers.parse('jag hämtar status för "{name}"'))
def status_for(mock_ctx, bridge, name):
    try:
        asyncio.run(get_mailbox_status(mock_ctx, name))
    except ValueError as e:
        bridge.errors.append(str(e))


@when("jag hämtar status för varje listad mapp")
def status_for_each(mock_ctx, bridge, mappar):
    for mapp in mappar:
        try:
            asyncio.run(get_mailbox_status(mock_ctx, mapp["name"]))
        except ValueError as e:
            bridge.errors.append(str(e))


@then(parsers.parse('ska mappen "{name}" finnas i listan'))
def folder_listed(mappar, name):
    names = [m["name"] for m in mappar]
    assert name in names, names


@then(parsers.re(rf'ska Bridge ha fått mappnamnet "{_WIRE}"$'))
def bridge_received(bridge, wire):
    assert bridge.errors == []
    assert bridge.imap._client.status.call_args.args[0] == f'"{wire}"'


@then("ska Bridge ha fått tillbaka exakt de namn som listades")
def bridge_received_all(bridge):
    assert bridge.errors == []
    sent = [c.args[0] for c in bridge.imap._client.status.call_args_list]
    assert sent == [f'"{w}"' for w in bridge.wire_names]

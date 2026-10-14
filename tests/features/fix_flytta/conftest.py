"""Gemensamma steg för flytt-, raderings- och mappscenarierna (fix-flytta).

Scenarierna kör de riktiga MCP-verktygen och den riktiga IMAPClient mot en
låtsas-Bridge (tests/fix_flytta_bridge.py), så det som kontrolleras är vilka
IMAP-kommandon Bridge faktiskt får.
"""
import asyncio

import pytest
from pytest_bdd import given, parsers, then

from tests.fix_flytta_bridge import make_client


@pytest.fixture
def bridge(monkeypatch, mock_ctx):
    imap, fake = make_client(monkeypatch)
    mock_ctx.request_context.lifespan_context.imap = imap
    fake.errors = []
    fake.result = None
    return fake


def run_tool(bridge, coro) -> None:
    """Kör ett verktyg och sparar resultatet eller felet på bridge."""
    try:
        bridge.result = asyncio.run(coro)
    except ValueError as e:
        bridge.errors.append(str(e))


@given(parsers.parse('att mejlet med UID "{uid}" ligger i "{mailbox}"'))
def mail_in(bridge, uid, mailbox):
    bridge.add(mailbox, uid)


@given(parsers.parse('att Bridge nekar {command} med "{text}"'))
def bridge_refuses(bridge, command, text):
    bridge.refuse[command] = text


@then("ska verktyget svara att det lyckades")
def tool_succeeded(bridge):
    assert bridge.errors == []
    assert bridge.result is True


@then(parsers.parse('ska verktyget ge ett fel som nämner "{text}"'))
def tool_failed(bridge, text):
    assert len(bridge.errors) == 1, bridge.errors
    assert text in bridge.errors[0], bridge.errors[0]


@then(parsers.parse('ska Bridge ha fått "{command}" med "{args}"'))
def bridge_got(bridge, command, args):
    sent = [" ".join(c[1:]) for c in bridge.sent(command)]
    assert args in sent, (command, bridge.commands)


@then(parsers.parse('ska Bridge inte ha fått "{command}"'))
def bridge_not_got(bridge, command):
    assert bridge.sent(command) == [], bridge.commands


@then("ska Bridge inte ha fått något skrivkommando")
def bridge_no_writes(bridge):
    writes = {"UID MOVE", "UID COPY", "UID STORE", "UID EXPUNGE", "EXPUNGE", "CREATE", "DELETE", "RENAME"}
    assert [c for c in bridge.commands if c[0] in writes] == [], bridge.commands

"""Gemensamma steg för efterfix-imap-scenarierna.

Scenarierna kör de riktiga MCP-verktygen och den riktiga IMAPClient mot
låtsas-Bridgen i tests/fix_flytta_bridge.py, så det som kontrolleras är vilka
IMAP-kommandon Bridge faktiskt får och vad verktyget svarar.
"""
import asyncio
import time
from types import SimpleNamespace

import pytest
from pytest_bdd import given, parsers, then, when

from protonmail_mcp.tools.mailboxes import get_mailbox_status
from protonmail_mcp.tools.messages import get_email, get_email_headers
from tests.fix_flytta_bridge import make_client


def unescape(text: str) -> str:
    """Feature-filerna skriver kontrolltecken som \\r och \\n."""
    return text.replace("\\r", "\r").replace("\\n", "\n")


@pytest.fixture
def bridge(monkeypatch, mock_ctx):
    imap, fake = make_client(monkeypatch)
    mock_ctx.request_context.lifespan_context.imap = imap
    fake.imap = imap
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


@given(parsers.parse('att mappen "{name}" finns och är tom'))
def empty_folder(bridge, name):
    bridge.mailboxes[name] = set()


@when(parsers.parse('jag hämtar mejlet med UID "{uid}" i "{mailbox}"'))
def fetch_mail(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, get_email(mock_ctx, uid=unescape(uid), mailbox=unescape(mailbox)))


@when(parsers.parse('jag hämtar status för "{mailbox}"'))
def fetch_status(mock_ctx, bridge, mailbox):
    run_tool(bridge, get_mailbox_status(mock_ctx, mailbox=unescape(mailbox)))


@then("ska verktyget svara att det lyckades")
def tool_succeeded(bridge):
    assert bridge.errors == []
    assert bridge.result is True


@then(parsers.parse('ska verktyget ge ett fel som nämner "{text}"'))
def tool_failed(bridge, text):
    assert len(bridge.errors) == 1, (bridge.errors, bridge.result)
    assert text in bridge.errors[0], bridge.errors[0]


@then("ska Bridge inte ha fått något kommando")
def bridge_untouched(bridge):
    # Inte ens NOOP eller en inloggning: valideringen ska komma först
    assert bridge.client.method_calls == [], bridge.client.method_calls


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


def install_bodies(bridge) -> None:
    """Låter låtsas-Bridgen svara på UID FETCH BODY.PEEK[...] med en literal.

    bridge.bodies[(mapp, uid)] = råa bytes. Övriga UID-kommandon går till
    låtsas-Bridgens vanliga hantering.
    """
    if hasattr(bridge, "bodies"):
        return
    bridge.bodies = {}
    original = bridge._uid

    async def uid(command, *args):
        if command.upper() == "FETCH" and len(args) > 1 and "BODY.PEEK" in args[1]:
            bridge.commands.append(("UID FETCH", *args))
            raw = bridge.bodies.get((bridge.selected, args[0]))
            if raw is None:
                return SimpleNamespace(result="OK", lines=[b"command completed"])
            return SimpleNamespace(result="OK", lines=[
                f"1 FETCH (UID {args[0]} BODY[] {{{len(raw)}}}".encode(), bytearray(raw), b")",
                b"command completed",
            ])
        return await original(command, *args)

    bridge.client.uid.side_effect = uid


@given(parsers.parse('att mejlet med UID "{uid}" i "{mailbox}" har ett ämne med {count:d} blanksteg mitt i'))
def mail_with_blank_subject(bridge, uid, mailbox, count):
    install_bodies(bridge)
    bridge.add(mailbox, uid)
    bridge.bodies[(mailbox, uid)] = b"Subject: a" + b" " * count + b"b\r\nFrom: x@example.com\r\n\r\n"


@when(parsers.parse('jag hämtar rubrikerna för UID "{uid}" i "{mailbox}"'))
def fetch_headers(mock_ctx, bridge, uid, mailbox):
    start = time.perf_counter()
    run_tool(bridge, get_email_headers(mock_ctx, uid=uid, mailbox=mailbox))
    bridge.elapsed = time.perf_counter() - start


@then(parsers.parse("ska svaret komma inom {seconds:g} sekund"))
def answered_within(bridge, seconds):
    assert bridge.errors == []
    assert bridge.elapsed < seconds, bridge.elapsed

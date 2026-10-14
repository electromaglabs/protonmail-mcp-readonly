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

from protonmail_mcp.tools.folders import delete_folder
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


@when(parsers.parse('jag tar bort mappen "{name}"'))
def delete(mock_ctx, bridge, name):
    run_tool(bridge, delete_folder(mock_ctx, name=name))


@when(parsers.parse('jag tar bort mappen "{name}" med force'))
def delete_force(mock_ctx, bridge, name):
    run_tool(bridge, delete_folder(mock_ctx, name=name, force=True))


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


def _ok(*lines):
    return SimpleNamespace(result="OK", lines=[*lines, b"command completed"])


def _no(text: str):
    return SimpleNamespace(result="NO", lines=[text.encode()])


def install_bodies(bridge) -> None:
    """Låter låtsas-Bridgen svara med innehåll på FETCH, UID FETCH BODY.PEEK och SEARCH.

    bridge.bodies[(mapp, uid)] = råa bytes (rubriker, ev. brödtext). Mejl
    utan eget innehåll får en enkel rubrik. bridge.refuse["FETCH"] gör att
    alla hämtningar nekas. Övriga UID-kommandon går till den vanliga hanteringen.
    """
    if hasattr(bridge, "bodies"):
        return
    bridge.bodies = {}
    original = bridge._uid

    def raw_for(uid):
        default = f"Subject: Brev {uid}\r\nFrom: x@example.com\r\n\r\n".encode()
        return bridge.bodies.get((bridge.selected, uid), default)

    def literal(seq, uid, what):
        raw = raw_for(uid)
        return [f"{seq} FETCH (UID {uid} FLAGS () {what} {{{len(raw)}}}".encode(), bytearray(raw), b")"]

    async def uid(command, *args):
        if command.upper() == "FETCH" and len(args) > 1 and "BODY.PEEK" in args[1]:
            bridge.commands.append(("UID FETCH", *args))
            if "FETCH" in bridge.refuse:
                return _no(bridge.refuse["FETCH"])
            if args[0] not in bridge.mailboxes.get(bridge.selected, set()):
                return _ok()
            return _ok(*literal(1, args[0], "BODY[]"))
        return await original(command, *args)

    def uids():
        return sorted(bridge.mailboxes.get(bridge.selected, set()), key=int)

    async def fetch(message_set, parts):
        bridge.commands.append(("FETCH", message_set, parts))
        if "FETCH" in bridge.refuse:
            return _no(bridge.refuse["FETCH"])
        lines = []
        for part in message_set.split(","):
            a, _, b = part.partition(":")
            for seq in range(int(a), int(b or a) + 1):
                lines += literal(seq, uids()[seq - 1], "BODY[HEADER]")
        return _ok(*lines)

    async def search(criteria):
        bridge.commands.append(("SEARCH", criteria))
        return _ok(" ".join(str(i) for i in range(1, len(uids()) + 1)).encode())

    bridge.client.uid.side_effect = uid
    bridge.client.fetch.side_effect = fetch
    bridge.client.search.side_effect = search


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

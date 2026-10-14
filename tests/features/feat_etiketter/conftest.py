"""Gemensamma steg för etikett-, stjärn- och massoperationsscenarierna (feat-etiketter).

Scenarierna kör de riktiga MCP-verktygen och den riktiga IMAPClient mot en
låtsas-Bridge med Protons etikettsemantik (tests/feat_etiketter_bridge.py),
så det som kontrolleras är vilka IMAP-kommandon Bridge faktiskt får och var
mejlen hamnar.
"""
import asyncio

import pytest
from pytest_bdd import given, parsers, then

from tests.feat_etiketter_bridge import make_client


@pytest.fixture
def bridge(monkeypatch, mock_ctx):
    imap, fake = make_client(monkeypatch)
    mock_ctx.request_context.lifespan_context.imap = imap
    return fake


def run_tool(bridge, coro) -> None:
    """Kör ett verktyg och sparar resultatet eller felet på bridge."""
    try:
        bridge.result = asyncio.run(coro)
    except ValueError as e:
        bridge.errors.append(str(e))


def uid_list(text: str) -> list[str]:
    return [u.strip() for u in text.split(",") if u.strip()]


@given(parsers.parse('att etiketten "{label}" finns'))
def label_exists(bridge, label):
    bridge.add_label(label)


@given(parsers.parse('att mejlet med UID "{uid}" och Message-ID "{mid}" ligger i "{mailbox}"'))
def mail_with_id_in(bridge, uid, mid, mailbox):
    bridge.put(mailbox, uid, mid)


@given(parsers.parse('att mejlen med UID "{uids}" ligger i "{mailbox}"'))
def mails_in(bridge, uids, mailbox):
    for uid in uid_list(uids):
        bridge.put(mailbox, uid)


@given(parsers.parse('att mejlet med Message-ID "{mid}" har etiketten "{label}" med UID "{uid}"'))
def mail_has_label(bridge, mid, label, uid):
    bridge.put(label, uid, mid)


@given(parsers.parse('att Bridge nekar {command} med "{text}"'))
def bridge_refuses(bridge, command, text):
    bridge.refuse[command] = text


@then("ska verktyget svara att det lyckades")
def tool_succeeded(bridge):
    assert bridge.errors == []
    assert bridge.result is True


@then(parsers.parse('ska verktyget ge ett fel som nämner "{text}"'))
def tool_failed(bridge, text):
    assert len(bridge.errors) == 1, (bridge.errors, bridge.result)
    assert text in bridge.errors[0], bridge.errors[0]


@then(parsers.parse('ska resultatet ha ok "{uids}" och inga misslyckade'))
def bulk_all_ok(bridge, uids):
    assert bridge.errors == []
    assert bridge.result == {"ok": uid_list(uids), "failed": []}


@then(parsers.parse('ska resultatet ha ok "{uids}" och UID "{bad}" misslyckat med "{text}"'))
def bulk_partly_ok(bridge, uids, bad, text):
    assert bridge.errors == []
    assert bridge.result["ok"] == uid_list(uids)
    assert [f["uid"] for f in bridge.result["failed"]] == [bad]
    assert text in bridge.result["failed"][0]["error"]


@then(parsers.parse('ska Bridge ha fått "{command}" med "{args}"'))
def bridge_got(bridge, command, args):
    sent = [" ".join(c[1:]) for c in bridge.sent(command)]
    assert args in sent, (command, bridge.commands)


@then(parsers.parse('ska Bridge inte ha fått "{command}" med "{args}"'))
def bridge_not_got_args(bridge, command, args):
    sent = [" ".join(c[1:]) for c in bridge.sent(command)]
    assert args not in sent, (command, bridge.commands)


@then(parsers.parse('ska Bridge inte ha fått "{command}"'))
def bridge_not_got(bridge, command):
    assert bridge.sent(command) == [], bridge.commands


@then("ska Bridge inte ha fått något skrivkommando")
def bridge_no_writes(bridge):
    assert bridge.writes() == [], bridge.commands


@then("ska Bridge inte ha fått något kommando")
def bridge_nothing(bridge):
    assert bridge.commands == [], bridge.commands


@then(parsers.parse('ska mejlet med Message-ID "{mid}" ligga i "{mailbox}"'))
def mail_is_in(bridge, mid, mailbox):
    assert mailbox in bridge.views_of(mid), bridge.views


@then(parsers.parse('ska mejlet med Message-ID "{mid}" inte ligga i "{mailbox}"'))
def mail_not_in(bridge, mid, mailbox):
    assert mailbox not in bridge.views_of(mid), bridge.views

"""Gemensamma steg för efterfix-slut: granskning 5 (identitet, Code=2501, lås, bästa försök, svar).

Scenarierna kör de riktiga MCP-verktygen och den riktiga IMAPClient mot
SlutBridge (tests/efterfix_slut_bridge.py): X-Pm-Internal-Id, mejl som inte
går att skilja åt på Message-ID, tid och storlek, och Code=2501 som i
Bridges connector.go.
"""
import asyncio

import pytest
from pytest_bdd import given, parsers, then

from protonmail_mcp import imap_client
from tests.efterfix_slut_bridge import make_client


@pytest.fixture
def bridge(monkeypatch, mock_ctx):
    monkeypatch.setattr(imap_client, "_GONE_TIMEOUT", 0.2)
    monkeypatch.setattr(imap_client, "_GONE_INTERVAL", 0.01)
    imap, fake = make_client(monkeypatch)
    mock_ctx.request_context.lifespan_context.imap = imap
    fake.twins = {}
    return fake


def run_tool(bridge, coro) -> None:
    try:
        bridge.result = asyncio.run(coro)
    except ValueError as e:
        bridge.errors.append(str(e))


def uid_list(text: str) -> list[str]:
    return [u.strip() for u in text.split(",") if u.strip()]


@given("att Bridge inte visar X-Pm-Internal-Id")
def no_internal_ids(bridge):
    bridge.internal_ids = False


@given(parsers.parse('att mejlet "{mid}" ligger i "{mailbox}" med UID "{uid}" och i All Mail med UID "{auid}"'))
def mail_in(bridge, mid, mailbox, uid, auid):
    bridge.put_mail(mailbox, uid, mid, all_mail_uid=auid)


@given(parsers.parse('att mejlet "{mid}" ligger i "{mailbox}" med UID "{uid}"'))
def mail_in_view(bridge, mid, mailbox, uid):
    bridge.put_mail(mailbox, uid, mid)


@given(parsers.parse('att samma Proton-mejl "{mid}" också syns i "{mailbox}" med UID "{uid}"'))
def same_mail_in(bridge, mid, mailbox, uid):
    bridge.put(mailbox, uid, mid)


@given(parsers.parse(
    'att ett annat mejl "{name}" med samma Message-ID "{mid}", tid och storlek ligger i "{mailbox}" med UID "{uid}"'
))
def twin_in(bridge, name, mid, mailbox, uid):
    bridge.twins[name] = bridge.put_twin(mailbox, uid, mid)


@given(parsers.parse('att mejlet "{name}" också syns i "{mailbox}" med UID "{uid}"'))
def twin_also_in(bridge, name, mailbox, uid):
    bridge.put(mailbox, uid, bridge.twins.get(name, name))


@then("ska verktyget svara att det lyckades")
def tool_ok(bridge):
    assert not bridge.errors, bridge.errors
    assert bridge.result is True or (isinstance(bridge.result, dict) and not bridge.result["failed"]), bridge.result


@then(parsers.parse('ska verktyget svara att UID "{uids}" lyckades'))
def bulk_ok(bridge, uids):
    assert not bridge.errors, bridge.errors
    assert bridge.result == {"ok": uid_list(uids), "failed": []}, bridge.result


@then(parsers.parse('ska svaret ha en förklaring som nämner "{text}"'))
def has_note(bridge, text):
    assert isinstance(bridge.result, dict) and text in bridge.result.get("note", ""), bridge.result


@then(parsers.parse('ska verktyget ge ett fel som nämner "{text}"'))
def tool_error(bridge, text):
    errors = list(bridge.errors)
    if isinstance(bridge.result, dict):
        errors += [f["error"] for f in bridge.result.get("failed", [])]
    assert any(text in e for e in errors), errors


@then(parsers.parse('ska inget UID ha lyckats'))
def none_ok(bridge):
    assert bridge.errors or (isinstance(bridge.result, dict) and not bridge.result["ok"]), bridge.result


@then(parsers.parse('ska mejlet "{mid}" bara ligga i "{views}"'))
def only_in(bridge, mid, views):
    assert sorted(bridge.views_of(bridge.twins.get(mid, mid))) == sorted(uid_list(views))


@then(parsers.parse('ska mejlet "{mid}" inte finnas i någon vy, inte heller All Mail'))
def gone(bridge, mid):
    assert bridge.views_of(bridge.twins.get(mid, mid)) == []


@then("ska Bridge inte ha fått några skrivkommandon")
def no_writes(bridge):
    assert not bridge.writes(), bridge.writes()


@then("ska Bridge aldrig ha fått EXPUNGE utan UID")
def no_plain_expunge(bridge):
    assert not bridge.sent("EXPUNGE")

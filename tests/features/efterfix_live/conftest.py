"""Gemensamma steg för efterfix-live: fynden från skrivtestet mot riktiga Bridge.

Scenarierna kör de riktiga MCP-verktygen och den riktiga IMAPClient mot
LiveBridge (tests/efterfix_live_bridge.py), som efterliknar det Bridge gjorde
live: Starred-vyn som släpar efter, NO på permanent radering som ändå raderar,
och utkast som blir föräldralösa i All Mail.
"""
import asyncio

import pytest
from pytest_bdd import given, parsers, then

from protonmail_mcp import imap_client
from tests.efterfix_live_bridge import make_client


@pytest.fixture
def bridge(monkeypatch, mock_ctx):
    monkeypatch.setattr(imap_client, "_GONE_TIMEOUT", 1.0, raising=False)
    monkeypatch.setattr(imap_client, "_GONE_INTERVAL", 0.0, raising=False)
    imap, fake = make_client(monkeypatch)
    mock_ctx.request_context.lifespan_context.imap = imap
    return fake


def run_tool(bridge, coro) -> None:
    try:
        bridge.result = asyncio.run(coro)
    except ValueError as e:
        bridge.errors.append(str(e))


def uid_list(text: str) -> list[str]:
    return [u.strip() for u in text.split(",") if u.strip()]


@given(parsers.parse('att mejlet "{mid}" är stjärnmärkt med UID "{uid}" i "{mailbox}" och UID "{suid}" i Starred'))
def starred_mail(bridge, mid, uid, mailbox, suid):
    bridge.put_mail(mailbox, uid, mid, flags=("\\Flagged",))
    bridge.put("Starred", suid, mid)


@given(parsers.parse('att mejlet "{mid}" ligger i "{mailbox}" med UID "{uid}" och i All Mail med UID "{auid}"'))
def mail_in(bridge, mid, mailbox, uid, auid):
    bridge.put_mail(mailbox, uid, mid, all_mail_uid=auid)


@given(parsers.parse('att utkastet "{mid}" ligger i "{mailbox}" med UID "{uid}" och i All Mail med UID "{auid}"'))
def draft_in(bridge, mid, mailbox, uid, auid):
    bridge.put_mail(mailbox, uid, mid, draft=True, all_mail_uid=auid)


@given(parsers.parse('att Bridge svarar NO med Code=2501 på permanent radering i "{mailbox}" men ändå raderar strax efteråt'))
def no_then_vanish(bridge, mailbox):
    bridge.no_then_vanish[mailbox] = [1, 1]


@given(parsers.parse('att Bridge svarar NO med Code=2501 på permanent radering i "{mailbox}" och mejlen blir kvar'))
def no_and_stays(bridge, mailbox):
    bridge.no_then_vanish[mailbox] = [10_000, 1]


@then("ska verktyget svara att det lyckades")
def tool_ok(bridge):
    assert not bridge.errors, bridge.errors
    assert bridge.result is True or (isinstance(bridge.result, dict) and not bridge.result["failed"]), bridge.result


@then(parsers.parse('ska verktyget svara att UID "{uids}" lyckades'))
def bulk_ok(bridge, uids):
    assert not bridge.errors, bridge.errors
    assert bridge.result == {"ok": uid_list(uids), "failed": []}


@then(parsers.parse('ska verktyget ge ett fel som nämner "{text}"'))
def tool_error(bridge, text):
    errors = list(bridge.errors)
    if isinstance(bridge.result, dict):
        errors += [f["error"] for f in bridge.result.get("failed", [])]
    assert any(text in e for e in errors), errors


@then(parsers.parse('ska mejlet "{mid}" bara ligga i "{views}"'))
def only_in(bridge, mid, views):
    assert bridge.views_of(mid) == uid_list(views)


@then(parsers.parse('ska mejlet "{mid}" inte finnas i någon vy, inte heller All Mail'))
def gone(bridge, mid):
    assert bridge.views_of(mid) == []


@then(parsers.parse('ska mejlet "{mid}" inte vara stjärnmärkt'))
def not_flagged(bridge, mid):
    assert "\\Flagged" not in bridge.messages[mid]["flags"]


@then("ska Bridge aldrig ha fått EXPUNGE utan UID")
def no_plain_expunge(bridge):
    assert not bridge.sent("EXPUNGE")

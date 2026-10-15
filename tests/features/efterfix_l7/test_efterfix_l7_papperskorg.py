"""BDD: delete_email/move_email rör inte ett mejl som redan ligger i Trash (L7)."""
import asyncio

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.manage import delete_email, move_email
from tests.efterfix_l7_bridge import make_client

scenarios("efterfix_l7_papperskorg.feature")


@pytest.fixture
def bridge(monkeypatch, mock_ctx):
    imap, fake = make_client(monkeypatch)
    mock_ctx.request_context.lifespan_context.imap = imap
    return fake


def _uids(text: str) -> list[str]:
    return [u.strip() for u in text.split(",") if u.strip()]


def _run(bridge, coro) -> None:
    try:
        bridge.result = asyncio.run(coro)
    except ValueError as exc:
        bridge.errors.append(str(exc))


@given(parsers.parse('att mejlet "{mid}" till mig själv ligger i "{a}" med UID "{ua}" och i "{b}" med UID "{ub}"'))
def note_to_self(bridge, mid, a, ua, b, ub):
    bridge.put(a, ua, mid)
    bridge.put(b, ub, mid)
    bridge.put("All Mail", "1000", mid)


@given(parsers.parse('att mejlet "{mid}" ligger i "{mailbox}" med UID "{uid}"'))
def mail_in(bridge, mid, mailbox, uid):
    bridge.put(mailbox, uid, mid, size=2000)


@given(parsers.parse('att ett mejl utan Message-ID ligger i "{mailbox}" med UID "{uid}"'))
def mail_without_message_id(bridge, mailbox, uid):
    bridge.put_without_message_id(mailbox, uid)


@when(parsers.parse('jag tar bort mejlet med UID "{uid}" i "{mailbox}"'))
def delete_one(mock_ctx, bridge, uid, mailbox):
    _run(bridge, delete_email(mock_ctx, uid=uid, mailbox=mailbox))


@when(parsers.parse('jag tar bort UID-listan "{uids}" i "{mailbox}"'))
def delete_many(mock_ctx, bridge, uids, mailbox):
    bridge.commands.clear()
    _run(bridge, delete_email(mock_ctx, uid=_uids(uids), mailbox=mailbox))


@when(parsers.parse('jag flyttar mejlet med UID "{uid}" i "{mailbox}" till "{target}"'))
def move_one(mock_ctx, bridge, uid, mailbox, target):
    _run(bridge, move_email(mock_ctx, uid=uid, target_mailbox=target, mailbox=mailbox))


@then(parsers.parse('ska verktyget svara att UID "{uid}" lyckades med förklaringen "{text}"'))
def ok_with_note(bridge, uid, text):
    assert not bridge.errors, bridge.errors
    assert isinstance(bridge.result, dict), bridge.result
    assert bridge.result["ok"] == [uid] and bridge.result["failed"] == []
    assert text in bridge.result["note"]


@then(parsers.parse('ska massvaret ha UID "{uids}" som lyckade och en förklaring som nämner UID "{uid}"'))
def bulk_ok_with_note(bridge, uids, uid):
    assert not bridge.errors, bridge.errors
    assert bridge.result["ok"] == _uids(uids)
    assert bridge.result["failed"] == []
    assert f"UID {uid}" in bridge.result["note"]
    assert "papperskorgen" in bridge.result["note"]


@then("ska verktyget svara True")
def answered_true(bridge):
    assert not bridge.errors, bridge.errors
    assert bridge.result is True


@then(parsers.parse('ska mejlet "{mid}" fortfarande ligga i "{mailbox}"'))
@then(parsers.parse('ska mejlet "{mid}" ligga i "{mailbox}"'))
def still_in(bridge, mid, mailbox):
    assert mid not in bridge.permanently_deleted, "mejlet raderades permanent"
    assert mailbox in bridge.views_of(mid)


@then(parsers.parse('ska Bridge inte ha fått någon flytt från "{mailbox}"'))
def no_move_from(bridge, mailbox):
    selected = None
    for cmd in bridge.commands:
        if cmd[0] == "SELECT":
            selected = cmd[1]
        elif cmd[0] in ("UID MOVE", "UID COPY"):
            assert selected != mailbox, cmd


def _searches_in(bridge, mailbox):
    selected, count = None, 0
    for cmd in bridge.commands:
        if cmd[0] == "SELECT":
            selected = cmd[1]
        elif cmd[0] == "SEARCH" and selected == mailbox:
            count += 1
    return count


@then(parsers.parse('ska Bridge ha fått exakt en sökning i "{mailbox}"'))
def one_search(bridge, mailbox):
    assert _searches_in(bridge, mailbox) == 1


@then(parsers.parse('ska Bridge inte ha sökt i "{mailbox}"'))
def no_search(bridge, mailbox):
    assert _searches_in(bridge, mailbox) == 0
    assert ("SELECT", mailbox) not in bridge.commands

"""BDD: gemensamma parametertyper (UID, bilagor, laxa tal/bool) i alla verktyg (llm-kontrakt, K7/K8)."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import imap_labels
from protonmail_mcp.tools import reply, send, threads
from tests import sdk_support as sdk
from tests.llm_kontrakt_support import client_session, text_of

scenarios("llm_kontrakt_parametertyper.feature")

UID_ARGS = {
    "get_email": {"mailbox": "INBOX"},
    "get_email_headers": {"mailbox": "INBOX"},
    "get_attachment": {"mailbox": "INBOX", "index": 0},
    "get_thread": {"mailbox": "INBOX"},
    "reply_to_email": {"mailbox": "INBOX", "body": "Hej"},
    "forward_email": {"mailbox": "INBOX", "to": "anna@example.com"},
    "create_reply_draft": {"mailbox": "INBOX", "body": "Hej"},
    "create_forward_draft": {"mailbox": "INBOX", "to": "anna@example.com"},
    "update_draft": {"mailbox": "Drafts", "to": "anna@example.com", "subject": "Hej", "body": "x"},
    "send_draft": {"mailbox": "Drafts"},
    "mark_email_read": {"mailbox": "INBOX"},
    "flag_email": {"mailbox": "INBOX"},
}
ATTACHMENT_ARGS = {
    "send_email": {"to": "anna@example.com", "subject": "Hej", "body": "x"},
    "reply_to_email": {"uid": "1", "mailbox": "INBOX", "body": "x"},
    "forward_email": {"uid": "1", "mailbox": "INBOX", "to": "anna@example.com"},
}
OTHER_ARGS = {"get_thread": {"uid": "1", "mailbox": "INBOX"}}


@pytest.fixture
def state(monkeypatch):
    imap = AsyncMock()
    seen = {"uids": [], "files": None}

    async def fake_thread(_imap, uid, mailbox, max_messages=50):
        seen["uids"].append(uid)
        return {"mailbox": mailbox, "messages": [], "total": 0, "complete": True, "note": None}

    async def fake_set_starred(_imap, mailbox, uids, starred):
        seen["uids"].extend(uids)
        return {"ok": list(uids), "failed": []}

    monkeypatch.setattr(threads, "fetch_thread", fake_thread)
    monkeypatch.setattr(imap_labels, "set_starred", fake_set_starred)
    return {"imap": imap, "smtp": AsyncMock(), "seen": seen}


def _call(monkeypatch, state, tool, args):
    async def run():
        async with client_session(monkeypatch, imap=state["imap"], smtp=state["smtp"]) as session:
            return await session.call_tool(tool, args)

    return asyncio.run(run())


@given("att det inte finns något mejl med UID 70")
def no_message(state):
    imap = state["imap"]
    imap.get_message.return_value = None
    imap.get_message_headers.return_value = None
    imap.set_flags.return_value = True


@when(parsers.parse("jag anropar {tool:w} med UID 70 som tal"), target_fixture="result")
def call_with_int_uid(monkeypatch, state, tool):
    return _call(monkeypatch, state, tool, {"uid": 70, **UID_ARGS[tool]})


@then(parsers.parse('ska UID:t ha tagits emot som "{uid}"'))
def uid_received(state, result, uid):
    text = text_of(result)
    assert "validation error" not in text and "Input should be" not in text, text
    imap = state["imap"]
    received = list(state["seen"]["uids"])
    for mock in (imap.get_message, imap.get_message_headers, imap.set_flags):
        received += [a for call in mock.call_args_list for a in call.args if a == uid]
    assert uid in received, (text, imap.mock_calls)


@when(parsers.parse('jag anropar {tool:w} med bilagan "{name}" som sträng'), target_fixture="result")
def call_with_single_attachment(monkeypatch, state, tool, name):
    def fake_load(paths):
        state["seen"]["files"] = paths
        raise ValueError("stoppad i testet")  # inget ska skickas

    monkeypatch.setattr(send, "load_for_sending", fake_load)
    monkeypatch.setattr(reply, "load_for_sending", fake_load)
    return _call(monkeypatch, state, tool, {**ATTACHMENT_ARGS[tool], "attachments": name})


@then(parsers.parse("ska bilagorna {expected} ha lästs in"))
def attachments_loaded(state, result, expected):
    assert "stoppad i testet" in text_of(result), text_of(result)
    assert state["seen"]["files"] == json.loads(expected)


@when(
    parsers.parse('jag anropar {tool:w} med {param:w} satt till strängen "{value}"'),
    target_fixture="result",
)
def call_with_string_value(monkeypatch, state, tool, param, value):
    state["imap"].search_messages.return_value = {
        "messages": [], "total": 0, "has_more": False, "complete": True, "note": None,
    }
    state["imap"].list_messages.return_value = {
        "messages": [], "total": 0, "page": 2, "pages": 0, "has_more": False,
    }
    return _call(monkeypatch, state, tool, {**OTHER_ARGS.get(tool, {}), param: value})


@then("ska anropet inte avvisas av valideringen")
def not_rejected(result):
    assert not sdk.wire(result).get("isError"), text_of(result)

"""Gemensamma steg för feat-sok-scenarierna (utökad sökning och get_thread).

Scenarierna kör de riktiga MCP-verktygen och den riktiga IMAPClient. Bara
aioimaplib-anslutningen är utbytt mot en falsk Bridge som söker i okodade
meddelanden, precis som riktiga Bridge.
"""
import asyncio

import pytest
from pytest_bdd import given, parsers, then, when

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.tools.search import search_emails
from tests.feat_sok_fakebridge import FakeBridge, FakeMessage


@pytest.fixture
def bridge(monkeypatch, mock_ctx):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    fake = FakeBridge()
    imap = IMAPClient(Settings())
    imap._client = fake.client()
    mock_ctx.request_context.lifespan_context.imap = imap
    return fake


@pytest.fixture
def outcome():
    return {}


def _rows(datatable):
    head, *rows = datatable
    return [dict(zip(head, row)) for row in rows]


@given(parsers.re(r'en brevlåda "?(?P<mailbox>[^"]+?)"? med mejlen$'))
def mailbox_with_messages(bridge, mailbox, datatable):
    for row in _rows(datatable):
        headers = {
            "From": row.get("from", ""),
            "To": row.get("to", ""),
            "Cc": row.get("cc", ""),
            "Subject": row.get("subject", ""),
            "Date": row.get("date", ""),
            "Message-ID": row.get("message_id", ""),
            "In-Reply-To": row.get("in_reply_to", ""),
            "References": row.get("references", ""),
        }
        message = FakeMessage(
            uid=int(row["uid"]),
            headers=headers,
            body=row.get("body", ""),
            # I tabellen utan backslash (Gherkin tolkar "\F" som escape): Flagged → \Flagged
            flags=["\\" + f for f in row["flags"].split()] if row.get("flags") else [],
            size=int(row.get("size") or 1000),
        )
        if row.get("content_type"):
            message.content_type = row["content_type"]
            message.parts = [p.strip() for p in row["parts"].split(",")]
        bridge.add(mailbox, message)


@given(parsers.parse('en brevlåda INBOX där UID "{uid}" är mejlet med Message-ID "{message_id}"'))
def inbox_with_message(bridge, uid, message_id):
    original = next(m for m in bridge.boxes["All Mail"] if m.header("Message-ID") == message_id)
    bridge.add("INBOX", FakeMessage(uid=int(uid), headers=dict(original.headers)))


def _search(mock_ctx, outcome, **kwargs):
    try:
        outcome["result"] = asyncio.run(search_emails(mock_ctx, mailbox="INBOX", **kwargs))
    except ValueError as exc:
        outcome["error"] = str(exc)


@when(parsers.re(r'jag söker i INBOX med (?P<name>\w+) "(?P<value>[^"]*)"$'))
def search_with_string(mock_ctx, bridge, outcome, name, value):
    _search(mock_ctx, outcome, **{name: value})


@when(parsers.re(r"jag söker i INBOX med (?P<name>\w+) (?P<value>true|false)$"))
def search_with_bool(mock_ctx, bridge, outcome, name, value):
    _search(mock_ctx, outcome, **{name: value == "true"})


@when(parsers.re(r"jag söker i INBOX med (?P<name>\w+) (?P<value>\d+)$"))
def search_with_int(mock_ctx, bridge, outcome, name, value):
    _search(mock_ctx, outcome, **{name: int(value)})


@when("jag söker i INBOX med en text som innehåller en radbrytning följd av ett IMAP-kommando")
def search_with_injection(mock_ctx, bridge, outcome):
    _search(mock_ctx, outcome, text="a\r\nX DELETE INBOX")


@then(parsers.parse('ska träffarna vara UID "{uids}"'))
def hits_are(outcome, uids):
    assert "error" not in outcome, outcome.get("error")
    expected = [u.strip() for u in uids.split(",")]
    assert [m["uid"] for m in outcome["result"]["messages"]] == expected


@then(parsers.parse('ska sökningen avvisas med "{text}"'))
def search_refused(outcome, text):
    assert text in outcome.get("error", ""), outcome


@then("ska inget sökkommando ha skickats till Bridge")
def no_search_sent(bridge):
    assert bridge.search_commands == []


# --- get_thread -------------------------------------------------------------

def _thread(mock_ctx, outcome, uid, **kwargs):
    from protonmail_mcp.tools.threads import get_thread

    try:
        outcome["result"] = asyncio.run(get_thread(mock_ctx, uid=uid, mailbox="INBOX", **kwargs))
    except ValueError as exc:
        outcome["error"] = str(exc)


@when(parsers.parse('jag hämtar konversationen för UID "{uid}" i INBOX'))
def fetch_thread(mock_ctx, bridge, outcome, uid):
    _thread(mock_ctx, outcome, uid)


@when(parsers.parse('jag hämtar konversationen för UID "{uid}" i INBOX med max_messages {limit:d}'))
def fetch_thread_limited(mock_ctx, bridge, outcome, uid, limit):
    _thread(mock_ctx, outcome, uid, max_messages=limit)


@then(parsers.parse('ska konversationen bestå av All Mail-UID "{uids}" i datumordning'))
def thread_is(outcome, uids):
    assert "error" not in outcome, outcome.get("error")
    expected = [u.strip() for u in uids.split(",")]
    assert [m["uid"] for m in outcome["result"]["messages"]] == expected


@then(parsers.parse('ska varje mejl ha mailbox "{mailbox}"'))
def every_message_in(outcome, mailbox):
    assert outcome["result"]["mailbox"] == mailbox
    assert all(m["mailbox"] == mailbox for m in outcome["result"]["messages"])


@then("ska konversationen vara komplett")
def thread_complete(outcome):
    assert outcome["result"]["complete"] is True


@then("ska konversationen inte vara komplett")
def thread_incomplete(outcome):
    assert outcome["result"]["complete"] is False
    assert outcome["result"]["note"]


@then(parsers.parse("ska konversationen innehålla {count:d} mejl"))
def thread_count(outcome, count):
    assert len(outcome["result"]["messages"]) == count


@then(parsers.parse('ska hämtningen avvisas med "{text}"'))
def thread_refused(outcome, text):
    assert text in outcome.get("error", ""), outcome

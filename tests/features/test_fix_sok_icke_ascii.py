"""BDD-tester: sökning på åäö och i RFC 2047-kodade headers (fix-sok, N4)."""
import asyncio

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp import imap_client as imap_module
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.tools.search import search_emails
from tests.fix_sok_fakebox import FakeMailbox, imap_mock

scenarios("fix_sok_icke_ascii.feature")


@pytest.fixture
def box(mock_ctx, monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    client = IMAPClient(Settings(_env_file=None))
    client._client = imap_mock()
    mock_ctx.request_context.lifespan_context.imap = client
    fake = FakeMailbox()
    fake.client = client
    return fake


@given(parsers.parse('att INBOX har brevet med UID "{uid}" och ämnet "{subject}"'))
def message_with_subject(box, uid, subject):
    box.add(uid, subject)


@given(parsers.parse('att INBOX har brevet med UID "{uid}" från "{sender}"'))
def message_from(box, uid, sender):
    box.add(uid, "Hej", sender)


@given(parsers.parse("att INBOX har {count:d} vanliga brev"))
def ordinary(box, count):
    box.fill(count)


@given(parsers.parse("att högst {limit:d} brev kontrolleras lokalt"))
def scan_limit(monkeypatch, limit):
    monkeypatch.setattr(imap_module, "_LOCAL_SCAN_LIMIT", limit)


def _search(mock_ctx, box, **kwargs):
    box.install(box.client)
    return asyncio.run(search_emails(mock_ctx, mailbox="INBOX", **kwargs))


@when(parsers.parse('jag söker på ämnet "{term}"'), target_fixture="result")
def search_subject(mock_ctx, box, term):
    return _search(mock_ctx, box, subject=term)


@when(parsers.parse('jag söker på avsändaren "{term}"'), target_fixture="result")
def search_from(mock_ctx, box, term):
    return _search(mock_ctx, box, from_addr=term)


@then(parsers.parse('ska träffarna vara UID "{uid}"'))
def hits_are(result, uid):
    assert [m["uid"] for m in result["messages"]] == [uid]


@then("ska sökningen vara fullständig")
def complete(result):
    assert result["complete"] is True


@then("ska sökningen inte vara fullständig")
def incomplete(result):
    assert result["complete"] is False


@then("ska svaret förklara att since eller before kan begränsa sökningen")
def explains(result):
    assert "since" in result["note"] and "before" in result["note"]

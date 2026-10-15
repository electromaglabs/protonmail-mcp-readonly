"""BDD: mailbox obligatorisk i get_email/get_email_headers, råa rubriker (llm-kontrakt, K4/K5)."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests import sdk_support as sdk
from tests.llm_kontrakt_support import client_session, text_of

scenarios("llm_kontrakt_lasverktyg_mailbox.feature")

RAW = b"From: a@example.com\r\nSubject: Hej\r\nMessage-ID: <m@x>\r\n\r\nText\r\n"


@pytest.fixture
def imap():
    imap = AsyncMock()
    imap.get_message.return_value = RAW
    imap.get_message_headers.return_value = {"from": "a@example.com", "subject": "Hej"}
    return imap


def _call(monkeypatch, imap, tool, args):
    async def run():
        async with client_session(monkeypatch, imap=imap) as session:
            return await session.call_tool(tool, args)

    return asyncio.run(run())


def _tools(monkeypatch):
    async def run():
        async with client_session(monkeypatch) as session:
            return {t.name: t for t in (await session.list_tools()).tools}

    return asyncio.run(run())


@given(parsers.parse('att "{mailbox}" har mejlet med UID "{uid}"'))
def has_message(imap, mailbox, uid):
    pass  # attrappen svarar för alla UID:n; kontrollen är vilken mapp som efterfrågas


@when(parsers.parse('jag anropar {tool:w} med uid "{uid}" utan mapp'), target_fixture="result")
def call_without_mailbox(monkeypatch, imap, tool, uid):
    return _call(monkeypatch, imap, tool, {"uid": uid})


@when(parsers.parse('jag anropar {tool:w} med uid "{uid}" i mappen "{mailbox}"'), target_fixture="result")
def call_with_mailbox(monkeypatch, imap, tool, uid, mailbox):
    return _call(monkeypatch, imap, tool, {"uid": uid, "mailbox": mailbox})


@when(parsers.parse("jag läser schemat för {tool:w}"), target_fixture="tool")
def read_schema(monkeypatch, tool):
    return _tools(monkeypatch)[tool]


@then("ska anropet avvisas för att mailbox saknas")
def rejected(result):
    assert sdk.wire(result).get("isError")
    assert "mailbox" in text_of(result)


@then("ska inget mejl ha lästs")
def nothing_read(imap):
    imap.get_message.assert_not_called()
    imap.get_message_headers.assert_not_called()


@then(parsers.parse('ska mejlet med UID "{uid}" ha lästs i "{mailbox}"'))
def read_in(imap, result, uid, mailbox):
    assert not sdk.wire(result).get("isError"), text_of(result)
    calls = imap.get_message.call_args_list + imap.get_message_headers.call_args_list
    assert [c.args for c in calls] == [(mailbox, uid)]


@then("ska mailbox vara obligatorisk utan standardvärde")
def mailbox_required(tool):
    schema = sdk.wire(tool)["inputSchema"]
    assert "mailbox" in schema["required"]
    assert "default" not in schema["properties"]["mailbox"]


@then("ska beskrivningen säga att UID:t gäller per mapp")
def says_per_folder(tool):
    assert "UID:n gäller per mapp" in tool.description


@then("ska beskrivningen säga att värdena är råa och att RFC 2047-kodade ord inte avkodas")
def says_raw(tool):
    assert "råa" in tool.description.lower() or "RÅA" in tool.description
    assert "RFC 2047" in tool.description and "avkodas inte" in tool.description


@then("ska beskrivningen säga att en rubrik som saknas inte finns med som nyckel")
def says_missing_keys(tool):
    assert "saknas" in tool.description and "nyckel" in tool.description


@then("ska beskrivningen hänvisa till get_email för läsbar text")
def refers_to_get_email(tool):
    assert "get_email" in tool.description.replace("get_email_headers", "")

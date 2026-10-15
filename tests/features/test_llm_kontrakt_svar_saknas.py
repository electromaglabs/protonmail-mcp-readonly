"""BDD: reply_to_email/forward_email på obefintligt UID kastar fel (llm-kontrakt, K1)."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests import sdk_support as sdk
from tests.llm_kontrakt_support import client_session, text_of

scenarios("llm_kontrakt_svar_saknas.feature")

ARGS = {
    "reply_to_email": {"body": "Hej"},
    "forward_email": {"to": "anna@example.com"},
}


@pytest.fixture
def mocks():
    return {"imap": AsyncMock(), "smtp": AsyncMock()}


@given(parsers.parse('att mappen "{mailbox}" inte har något mejl med UID "{uid}"'))
def missing(mocks, mailbox, uid):
    mocks["imap"].get_message.return_value = None


@when(parsers.parse('jag anropar {tool:w} med uid "{uid}" i mappen "{mailbox}"'), target_fixture="result")
def call(monkeypatch, mocks, tool, uid, mailbox):
    async def run():
        async with client_session(monkeypatch, imap=mocks["imap"], smtp=mocks["smtp"]) as session:
            return await session.call_tool(tool, {"uid": uid, "mailbox": mailbox, **ARGS[tool]})

    return asyncio.run(run())


@then(parsers.parse('ska anropet misslyckas med texten "{text}"'))
def fails_with(result, text):
    assert sdk.wire(result).get("isError"), text_of(result)
    assert text in text_of(result)


@then("ska felet säga att UID:n gäller per mapp")
def per_folder(result):
    assert "UID:n gäller per mapp" in text_of(result)


@then("ska inget mejl ha skickats")
def nothing_sent(mocks):
    mocks["smtp"].send_email.assert_not_called()

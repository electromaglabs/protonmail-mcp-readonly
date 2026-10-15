"""BDD: central felomslutning av verktygen, sett via MCP-klienten (llm-kontrakt)."""
import asyncio
import logging
from unittest.mock import AsyncMock

import aioimaplib
import aiosmtplib
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.imap_client import IMAPAuthenticationError
from protonmail_mcp.smtp_client import SMTPPartialDeliveryError
from tests.llm_kontrakt_support import client_session, text_of

scenarios("llm_kontrakt_felmeddelanden.feature")

CONNECTION_ERRORS = {
    "anslutning nekad": ConnectionRefusedError(61, "Connect call failed ('127.0.0.1', 1143)"),
    "timeout": asyncio.TimeoutError(),
    "avbruten anslutning": ConnectionResetError("Connection lost"),
    "aioimaplib-protokoll": aioimaplib.Abort("socket error: EOF"),
}


@pytest.fixture
def mocks():
    return {"imap": AsyncMock(), "smtp": AsyncMock()}


def _call(monkeypatch, mocks, name, args):
    async def run():
        async with client_session(monkeypatch, imap=mocks["imap"], smtp=mocks["smtp"]) as session:
            return await session.call_tool(name, args)

    return asyncio.run(run())


@given(parsers.parse('att Bridge avvisar anropet med felet "{message}"'))
def bridge_rejects(mocks, message):
    mocks["imap"].list_mailboxes.side_effect = ValueError(message)


@given(parsers.parse("att anslutningen till Bridge misslyckas med {kind}"))
def connection_fails(mocks, kind):
    mocks["imap"].list_mailboxes.side_effect = CONNECTION_ERRORS[kind]


@given("att Bridge nekar inloggningen över IMAP")
def imap_auth_fails(mocks):
    mocks["imap"].list_mailboxes.side_effect = IMAPAuthenticationError(
        "Inloggningen mot ProtonMail Bridge misslyckades (NO [AUTHENTICATIONFAILED])"
    )


@given("att Bridge nekar inloggningen över SMTP")
def smtp_auth_fails(mocks):
    mocks["smtp"].send_email.side_effect = aiosmtplib.SMTPAuthenticationError(535, "authentication failed")


@given(parsers.parse('att servern levererar till "{delivered}" men vägrar "{refused}"'))
def partial_delivery(mocks, delivered, refused):
    mocks["smtp"].send_email.side_effect = SMTPPartialDeliveryError(
        refused={refused: (550, "No such user")}, delivered=[delivered]
    )


@given("att anslutningen bryts när mejlet skickas")
def send_disconnects(mocks):
    mocks["smtp"].send_email.side_effect = aiosmtplib.SMTPServerDisconnected("Unexpected EOF received")


@given(parsers.parse('att ett oväntat internt fel med texten "{message}" inträffar'))
def unexpected(mocks, message):
    mocks["imap"].list_mailboxes.side_effect = RuntimeError(message)


@when("jag anropar list_mailboxes", target_fixture="result")
def call_list_mailboxes(monkeypatch, mocks, caplog):
    caplog.set_level(logging.ERROR)
    return _call(monkeypatch, mocks, "list_mailboxes", {})


@when(parsers.parse('jag skickar ett mejl till "{first}" och "{second}"'), target_fixture="result")
def send_two(monkeypatch, mocks, first, second):
    return _call(monkeypatch, mocks, "send_email", {"to": [first, second], "subject": "Hej", "body": "x"})


@when(parsers.parse('jag skickar ett mejl till "{to}"'), target_fixture="result")
def send_one(monkeypatch, mocks, to):
    return _call(monkeypatch, mocks, "send_email", {"to": to, "subject": "Hej", "body": "x"})


@then(parsers.parse('ska anropet misslyckas med texten "{text}"'))
def fails_with(result, text):
    assert result.isError, text_of(result)
    assert text in text_of(result)


@then("ska felet inte innehålla något stackspår")
def no_traceback(result):
    text = text_of(result)
    assert "Traceback" not in text and 'File "' not in text


@then("ska felet fråga om Bridge körs")
def asks_if_bridge_runs(result):
    assert "körs Bridge?" in text_of(result)


@then("ska felet nämna Bridge-lösenordet")
def mentions_bridge_password(result):
    assert "Bridge-lösenord" in text_of(result)


@then(parsers.parse('ska felet nämna att "{addr}" inte fick mejlet'))
def mentions_refused(result, addr):
    text = text_of(result)
    assert addr in text
    assert "550 No such user" in text


@then("ska felet säga att mejlet inte ska skickas om till alla")
def no_resend(result):
    assert "Skicka inte om" in text_of(result)


@then("ska felet säga att mejlet kan ha skickats och att Sent ska kontrolleras")
def maybe_sent(result):
    text = text_of(result)
    assert "kan ha skickats" in text and "Sent" in text


@then(parsers.parse('ska felet inte innehålla texten "{text}"'))
def not_containing(result, text):
    assert text not in text_of(result)


@then("ska felet vara loggat till stderr med stackspår")
def logged_with_traceback(caplog):
    records = [r for r in caplog.records if r.levelno >= logging.ERROR and "list_mailboxes" in r.getMessage()]
    assert records, caplog.text
    assert "Traceback" in records[0].getMessage() and "intern detalj" in records[0].getMessage()

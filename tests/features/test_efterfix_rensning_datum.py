"""BDD: date_iso följer RFC 5322 (efterfix-rensning, F12)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.messages import get_email

scenarios("efterfix_rensning_datum.feature")


@given(parsers.parse('ett mejl med datumet "{date}"'), target_fixture="raw")
def mail(mock_ctx, date):
    raw = f"From: a@b.se\r\nDate: {date}\r\n\r\nx\r\n".encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@when("jag hämtar mejlet med get_email", target_fixture="result")
def fetch(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX"))


@then(parsers.parse('ska date_iso vara "{iso}"'))
def iso_is(result, iso):
    assert result["date_iso"] == iso

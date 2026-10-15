"""BDD: date_iso i get_email och listningar (llm-injektion)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.imap_client import _parse_fetch_metadata
from protonmail_mcp.tools.messages import get_email

scenarios("llm_injektion_datum.feature")


@given(parsers.parse('ett mejl med datumet "{date}"'), target_fixture="raw")
def mail_dated(mock_ctx, date):
    raw = f"From: a@b.se\r\nDate: {date}\r\n\r\nx\r\n".encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@given(parsers.parse('en IMAP-sida med ett mejl daterat "{date}"'), target_fixture="fetch_lines")
def imap_page(date):
    header = f"From: a@b.se\r\nDate: {date}\r\n\r\n".encode()
    return [b"* 1 FETCH (UID 3 FLAGS () BODY[HEADER] {%d}" % len(header), bytearray(header), b")"]


@when("jag hämtar mejlet med get_email", target_fixture="result")
def fetch(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX"))


@when("sidans metadata parsas", target_fixture="listing")
def parse_page(fetch_lines):
    return _parse_fetch_metadata(fetch_lines)


@then(parsers.parse('ska date_iso vara "{iso}"'))
def iso_is(result, iso):
    assert result["date_iso"] == iso


@then("ska date_iso vara null")
def iso_null(result):
    assert result["date_iso"] is None


@then(parsers.parse('det råa datumet ska vara "{date}"'))
def raw_date(result, date):
    assert result["date"] == date


@then(parsers.parse('ska listningens date_iso vara "{iso}"'))
def listing_iso(listing, iso):
    assert listing[0]["date_iso"] == iso

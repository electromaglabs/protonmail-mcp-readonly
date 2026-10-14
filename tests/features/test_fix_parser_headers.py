"""BDD-tester för avkodning av rubriker (fix-parser)."""
import asyncio

from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.imap_client import _parse_fetch_metadata
from protonmail_mcp.tools.messages import get_email

scenarios("fix_parser_headers.feature")


@given(parsers.parse('ett mejl med rubrikraden "{line}"'), target_fixture="raw")
def mail_with_header(mock_ctx, line):
    raw = f"From: a@b.se\r\n{line}\r\n\r\nbody\r\n".encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@when("jag hämtar mejlet med get_email", target_fixture="result")
def fetch_mail(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1"))


@then(parsers.parse('ska ämnet vara "{subject}"'))
def subject_is(result, subject):
    assert result["subject"] == subject


@given(
    parsers.parse('en IMAP-sida med tre mejl där det mittersta har ämnet "{subject}"'),
    target_fixture="fetch_lines",
)
def imap_page(subject):
    lines = []
    for uid, subj in [(1, "ok"), (2, subject), (3, "ok")]:
        lines.append(f"* {uid} FETCH (UID {uid} FLAGS () BODY[HEADER] {{10}}".encode())
        lines.append(bytearray(f"Subject: {subj}\r\n\r\n".encode()))
    return lines


@when("sidans metadata parsas", target_fixture="listing")
def parse_page(fetch_lines):
    return _parse_fetch_metadata(fetch_lines)


@then(parsers.parse("ska {count:d} mejl listas"))
def listed_count(listing, count):
    assert len(listing) == count


@then(parsers.parse('det mittersta mejlets ämne ska vara "{subject}"'))
def middle_subject(listing, subject):
    assert listing[1]["subject"] == subject

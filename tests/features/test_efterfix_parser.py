"""BDD-tester för fynden från granskningen efter buggfixarna (efterfix-parser)."""
import asyncio
import time

from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.imap_client import _parse_fetch_metadata
from protonmail_mcp.tools.messages import get_email

scenarios("efterfix_parser.feature")


@given(parsers.parse('ett mejl med rubrikraden "{line}"'), target_fixture="raw")
def mail_with_header(mock_ctx, line):
    raw = f"From: a@b.se\r\n{line}\r\n\r\nbody\r\n".encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@when("jag hämtar mejlet med get_email", target_fixture="result")
def fetch_mail(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX"))


@then(parsers.parse('ska ämnet vara "{subject}"'))
def subject_is(result, subject):
    assert result["subject"] == subject


@given(
    parsers.parse(
        'en IMAP-sida med ett mejl vars ämne är {count:d} vikta rader med "{chunk}" utan avslutning'
    ),
    target_fixture="fetch_lines",
)
def imap_page_with_huge_subject(count, chunk):
    # Varje rad är under 998 tecken, så rubriken följer RFC 5322
    header = ("Subject: " + "\r\n ".join([chunk * 128] * count) + "\r\n\r\n").encode()
    return [
        b"* 1 FETCH (UID 1 FLAGS () BODY[HEADER] {%d}" % len(header),
        bytearray(header),
        b")",
    ]


@when("sidans metadata parsas och tiden mäts", target_fixture="timed_listing")
def parse_page_timed(fetch_lines):
    start = time.perf_counter()
    listing = _parse_fetch_metadata(fetch_lines)
    return listing, time.perf_counter() - start


@then(parsers.parse("ska det ta under {seconds:d} sekund"))
def took_less_than(timed_listing, seconds):
    _, elapsed = timed_listing
    assert elapsed < seconds, f"tog {elapsed:.2f} s"


@then(parsers.parse('ämnet ska börja med "{prefix}"'))
def subject_starts_with(timed_listing, prefix):
    listing, _ = timed_listing
    assert listing[0]["subject"].startswith(prefix)


@given(parsers.parse("ett mejl med rubrikraden '{line}'"), target_fixture="raw")
def mail_with_header_single_quoted(mock_ctx, line):
    return mail_with_header(mock_ctx, line)


@then(parsers.parse("ska mottagarens adress vara '{addr}'"))
def recipient_address_is(result, addr):
    assert [a for _, a in result["addresses"]["to"]] == [addr]


@then(parsers.parse("mottagaren ska visas som '{formatted}'"))
def recipient_shown_as(result, formatted):
    assert result["to"] == [formatted]


@given(parsers.parse("ett HTML-brev med innehållet '{markup}'"), target_fixture="raw")
def html_mail(mock_ctx, markup):
    raw = (
        "From: a@b.se\r\nSubject: s\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
        + markup
        + "\r\n"
    ).encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@when("jag hämtar mejlet som text med get_email", target_fixture="result")
def fetch_mail_as_text(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX", body_format="text", max_length=None))


@then(parsers.parse("ska brödtexten vara '{body}'"))
def body_is(result, body):
    assert result["body_plain"] == body


@given(
    parsers.parse('ett mejl märkt "{charset}" med brödtexten "{text}" kodad som utf-8'),
    target_fixture="raw",
)
def mail_with_mislabelled_charset(mock_ctx, charset, text):
    body = text.encode()
    assert len(body) % 2 == 0  # udda längd kan aldrig avkodas som utf-16
    raw = (
        f"From: a@b.se\r\nSubject: s\r\nContent-Type: text/plain; charset={charset}\r\n"
        "Content-Transfer-Encoding: 8bit\r\n\r\n"
    ).encode() + body
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw

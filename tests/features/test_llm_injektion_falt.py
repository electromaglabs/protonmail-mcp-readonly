"""BDD: avsändarstyrda fält rensas i get_email och listningar (llm-injektion)."""
import asyncio
import re
from email.header import Header
from email.message import EmailMessage

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.imap_client import _parse_fetch_metadata
from protonmail_mcp.tools.messages import get_email

scenarios("llm_injektion_falt.feature")


def _chars(text: str) -> str:
    """{U+200B} i feature-filen blir tecknet U+200B."""
    return re.sub(r"\{U\+([0-9A-F]{4,6})\}", lambda m: chr(int(m.group(1), 16)), text)


def _tags(text: str) -> str:
    return "".join(chr(0xE0000 + ord(ch)) for ch in text)


def _encoded(text: str) -> str:
    return Header(text, "utf-8").encode()


def _serve(mock_ctx, raw: bytes) -> bytes:
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@given(
    parsers.parse('ett mejl med ämnet "{subject}" följt av taggtecken som stavar "{hidden}"'),
    target_fixture="raw",
)
def mail_with_tagged_subject(mock_ctx, subject, hidden):
    raw = f"From: a@b.se\r\nSubject: {_encoded(subject + _tags(hidden))}\r\n\r\nbody\r\n"
    return _serve(mock_ctx, raw.encode())


@given(parsers.parse('ett mejl från "{name}" med adressen "{addr}"'), target_fixture="raw")
def mail_from(mock_ctx, name, addr):
    raw = f"From: {_encoded(_chars(name))} <{addr}>\r\nSubject: x\r\n\r\nbody\r\n"
    return _serve(mock_ctx, raw.encode())


@given(parsers.parse('ett mejl med brödtexten "{body}"'), target_fixture="raw")
def mail_with_body(mock_ctx, body):
    msg = EmailMessage()
    msg["From"] = "a@b.se"
    msg.set_content(_chars(body))
    return _serve(mock_ctx, msg.as_bytes())


@given(parsers.parse('ett HTML-mejl med innehållet "{html}"'), target_fixture="raw")
def html_mail(mock_ctx, html):
    raw = f"From: a@b.se\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{html}\r\n"
    return _serve(mock_ctx, raw.encode())


@given(parsers.parse('ett mejl med en bilaga som heter "{name}"'), target_fixture="raw")
def mail_with_attachment(mock_ctx, name):
    msg = EmailMessage()
    msg["From"] = "a@b.se"
    msg.set_content("se bilaga")
    msg.add_attachment(b"%PDF", maintype="application", subtype="octet-stream", filename=_chars(name))
    return _serve(mock_ctx, msg.as_bytes())


@given(
    parsers.parse('en IMAP-sida med ett mejl från "{sender}" med ämnet "{subject}"'),
    target_fixture="fetch_lines",
)
def imap_page(sender, subject):
    header = f"From: {_chars(sender)}\r\nSubject: {_chars(subject)}\r\n\r\n".encode()
    return [b"* 1 FETCH (UID 7 FLAGS () BODY[HEADER] {%d}" % len(header), bytearray(header), b")"]


@when("jag hämtar mejlet med get_email", target_fixture="result")
def fetch_mail(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX"))


@when("sidans metadata parsas", target_fixture="listing")
def parse_page(fetch_lines):
    return _parse_fetch_metadata(fetch_lines)


@then(parsers.parse('ska ämnet vara "{subject}"'))
def subject_is(result, subject):
    assert result["subject"] == subject


@then(parsers.parse('ska avsändaren vara "{sender}"'))
def sender_is(result, sender):
    assert result["from"] == sender


@then(parsers.parse('avsändarens adress ska vara "{addr}"'))
def sender_address_is(result, addr):
    assert result["addresses"]["from"][0][1] == addr


@then(parsers.parse('ska brödtexten vara "{body}"'))
def body_is(result, body):
    assert result["body_plain"].strip() == body


@then(parsers.parse('ska bilagan heta "{name}"'))
def attachment_named(result, name):
    assert [a["filename"] for a in result["attachments"]] == [name]


@then(parsers.parse('ska listningens ämne vara "{subject}"'))
def listing_subject(listing, subject):
    assert listing[0]["subject"] == subject


@then(parsers.parse('listningens avsändare ska vara "{sender}"'))
def listing_sender(listing, sender):
    assert listing[0]["from"] == _chars(sender)

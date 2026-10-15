"""BDD: injektionsvarningen läser fler fält och varianter (efterfix-rensning, F11)."""
import asyncio
from email.message import EmailMessage

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.imap_client import _parse_fetch_metadata
from protonmail_mcp.tools.messages import get_email

scenarios("efterfix_rensning_heuristik.feature")


def _serve(mock_ctx, msg: EmailMessage) -> bytes:
    raw = msg.as_bytes()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


def _base() -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "a@x.se"
    msg["To"] = "me@x.se"
    msg["Subject"] = "Hej"
    msg.set_content("Hej!")
    return msg


@given(parsers.parse('ett mejl från "{name}" <{addr}>'), target_fixture="raw")
def from_name(mock_ctx, name, addr):
    msg = _base()
    msg.replace_header("From", f'"{name}" <{addr}>')
    return _serve(mock_ctx, msg)


@given(parsers.parse('ett mejl med bilagan "{filename}"'), target_fixture="raw")
def with_attachment(mock_ctx, filename):
    msg = _base()
    msg.add_attachment(b"x", maintype="text", subtype="plain", filename=filename)
    return _serve(mock_ctx, msg)


@given(parsers.parse('ett mejl med ämnet "{subject}"'), target_fixture="raw")
def with_subject(mock_ctx, subject):
    msg = _base()
    msg.replace_header("Subject", subject)
    return _serve(mock_ctx, msg)


@when("jag hämtar mejlet med get_email", target_fixture="result")
def fetch(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX"))


@then(parsers.parse('ska suspicious_content nämna "{label}"'))
def mentions(result, label):
    assert any(label in r for r in result["suspicious_content"]), result["suspicious_content"]


@given(parsers.parse('en listning där avsändaren heter "{name}"'), target_fixture="raw")
def listing(name):
    hdr = f'From: "{name}" <a@x.se>\r\nSubject: Hej\r\n\r\n'.encode()
    return [f"1 FETCH (UID 7 FLAGS () BODY[HEADER] {{{len(hdr)}}}".encode(), bytearray(hdr), b")"]


@when("jag läser raden", target_fixture="result")
def read_row(raw):
    return _parse_fetch_metadata(raw)[0]


@then(parsers.parse('ska raden ha suspicious_content som nämner "{label}"'))
def row_mentions(result, label):
    assert any(label in r for r in result["suspicious_content"])

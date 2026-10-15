"""BDD: typiska injektionsmönster flaggas i get_email (llm-injektion)."""
import asyncio
import re
from email.header import Header
from email.message import EmailMessage

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.messages import get_email

scenarios("llm_injektion_misstankt.feature")


def _chars(text: str) -> str:
    return re.sub(r"\{U\+([0-9A-F]{4,6})\}", lambda m: chr(int(m.group(1), 16)), text)


def _serve(mock_ctx, raw: bytes) -> bytes:
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@given(parsers.parse('ett mejl med brödtexten "{body}"'), target_fixture="raw")
def mail_with_body(mock_ctx, body):
    msg = EmailMessage()
    msg["From"] = "a@b.se"
    msg["Subject"] = "Hej"
    msg.set_content(_chars(body))
    return _serve(mock_ctx, msg.as_bytes())


@given(parsers.parse("ett HTML-mejl med innehållet '{html}'"), target_fixture="raw")
def html_mail(mock_ctx, html):
    raw = f"From: a@b.se\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{html}\r\n".encode()
    return _serve(mock_ctx, raw)


@given(
    parsers.parse('ett mejl med ämnet "{subject}" följt av taggtecken som stavar "{hidden}"'),
    target_fixture="raw",
)
def mail_with_tagged_subject(mock_ctx, subject, hidden):
    tags = "".join(chr(0xE0000 + ord(ch)) for ch in hidden)
    raw = f"From: a@b.se\r\nSubject: {Header(subject + tags, 'utf-8').encode()}\r\n\r\nbody\r\n"
    return _serve(mock_ctx, raw.encode())


@when("jag hämtar mejlet med get_email", target_fixture="result")
def fetch(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX", max_length=None))


@then(parsers.parse('ska suspicious_content nämna "{phrase}"'))
@then(parsers.parse('suspicious_content ska nämna "{phrase}"'))
def mentions(result, phrase):
    assert any(phrase in reason for reason in result["suspicious_content"]), result["suspicious_content"]


@then("ska suspicious_content vara tom")
def empty(result):
    assert result["suspicious_content"] == []


@then(parsers.parse('brödtexten ska fortfarande innehålla "{text}"'))
def body_contains(result, text):
    assert text in result["body_plain"]


@then(parsers.parse('brödtexten ska vara "{text}"'))
def body_is(result, text):
    assert result["body_plain"] == text


@then(parsers.parse("hidden_html ska ange {count:d} gömt element"))
def hidden_count(result, count):
    assert result["hidden_html"]["elements"] == count

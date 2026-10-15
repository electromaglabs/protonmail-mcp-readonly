"""BDD-steg för efterfix_skick_bilaga_text.feature."""
import asyncio
import re
from unittest.mock import AsyncMock, MagicMock

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.attachments import get_attachment
from tests.feat_bilagor_support import attachment_env, base64_part, multipart, raw_message, text_part  # noqa: F401

scenarios("efterfix_skick_bilaga_text.feature")


def _decode(text: str) -> str:
    return re.sub(r"\[U\+([0-9A-Fa-f]{4,6})\]", lambda m: chr(int(m.group(1), 16)), text)


@given(
    parsers.parse('ett mejl med textbilagan "{filename}" med innehållet "{content}"'),
    target_fixture="raw",
)
def mail_with_text_attachment(attachment_env, filename, content):  # noqa: F811
    from email.header import Header

    encoded_name = Header(_decode(filename), "utf-8").encode()
    return raw_message(multipart(text_part(), base64_part(
        "text/plain; charset=utf-8", f'; filename="{encoded_name}"', _decode(content).encode("utf-8")
    )))


@when(parsers.parse("LLM:en läser bilaga {index:d} direkt"), target_fixture="result")
def read_attachment(raw, index):
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return asyncio.run(get_attachment(ctx, uid="1", mailbox="INBOX", index=index, save=False))


@then(parsers.parse('ska innehållet vara "{text}"'))
def content_is(result, text):
    assert result["encoding"] == "text"
    assert result["content"] == text


@then("ska svaret ha untrusted_content_notice")
def has_notice(result):
    assert "opålitligt" in result["untrusted_content_notice"]


@then(parsers.parse("ska sanitized ange att {count:d} tecken togs bort ur innehållet"))
def sanitized_count(result, count):
    assert result["sanitized"] == {"content": count}


@then("ska sanitized vara tom")
def sanitized_empty(result):
    assert result["sanitized"] == {}


@then(parsers.parse('ska filnamnet i svaret vara "{name}"'))
def filename_is(result, name):
    assert result["filename"] == name

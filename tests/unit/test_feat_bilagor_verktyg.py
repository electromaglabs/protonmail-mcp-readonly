"""Enhetstester för verktyget get_attachment."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.server import mcp
from protonmail_mcp.tools.attachments import get_attachment
from tests.feat_bilagor_support import (  # noqa: F401
    attachment_env,
    base64_part,
    multipart,
    raw_message,
    text_part,
)


def _ctx(raw):
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return ctx


def _run(raw, **kwargs):
    kwargs.setdefault("uid", "1")
    kwargs.setdefault("mailbox", "INBOX")
    kwargs.setdefault("index", 0)
    return asyncio.run(get_attachment(_ctx(raw), **kwargs))


def test_schema_requires_mailbox_and_non_negative_index():
    tool = mcp._tool_manager.get_tool("get_attachment")
    schema = tool.parameters
    assert set(schema["required"]) >= {"uid", "mailbox", "index"}
    assert schema["properties"]["index"]["minimum"] == 0
    assert schema["properties"]["save"]["default"] is True


def test_attached_email_is_saved_as_eml(attachment_env):
    root, _ = attachment_env
    raw = raw_message(multipart(text_part(), "Content-Type: message/rfc822\r\n\r\nSubject: inre\r\n\r\nx\r\n"))
    result = _run(raw)
    assert result["path"].endswith("bilaga.eml")
    assert (root / "bilaga.eml").read_bytes().startswith(b"Subject: inre")


def test_text_with_unknown_charset_does_not_raise(attachment_env):
    raw = raw_message(multipart(text_part(), base64_part(
        "text/plain; charset=x-okand", '; filename="a.txt"', "åäö".encode("utf-8")
    )))
    result = _run(raw, save=False)
    assert result["encoding"] == "text"
    assert result["content"] == "åäö"


def test_text_over_limit_is_rejected(attachment_env, monkeypatch):
    from protonmail_mcp.config import get_settings

    monkeypatch.setenv("PROTONMAIL_ATTACHMENT_MAX_INLINE_BYTES", "3")
    get_settings.cache_clear()
    raw = raw_message(multipart(text_part(), base64_part("text/plain", '; filename="a.txt"', b"abcd")))
    with pytest.raises(ValueError, match="save=True"):
        _run(raw, save=False)


def test_limit_is_inclusive(attachment_env, monkeypatch):
    from protonmail_mcp.config import get_settings

    monkeypatch.setenv("PROTONMAIL_ATTACHMENT_MAX_INLINE_BYTES", "4")
    get_settings.cache_clear()
    raw = raw_message(multipart(text_part(), base64_part("text/plain", '; filename="a.txt"', b"abcd")))
    assert _run(raw, save=False)["content"] == "abcd"


def test_saved_result_has_no_content_and_keeps_original_filename(attachment_env):
    raw = raw_message(multipart(text_part(), base64_part(
        "application/pdf", '; filename="../x.pdf"', b"%PDF"
    )))
    result = _run(raw)
    assert "content" not in result
    assert result["filename"] == "../x.pdf"
    assert result["saved_as"] == "x.pdf"
    assert result["part"] == "2"


def test_invalid_uid_is_rejected_before_fetch(attachment_env):
    from protonmail_mcp.imap_client import _validate_uid  # noqa: F401 — finns

    ctx = _ctx(None)
    ctx.request_context.lifespan_context.imap.get_message.side_effect = ValueError("Ogiltigt UID")
    with pytest.raises(ValueError, match="UID"):
        asyncio.run(get_attachment(ctx, uid="1:*", mailbox="INBOX", index=0))


def test_not_found_names_mailbox(attachment_env):
    with pytest.raises(ValueError, match="Inget meddelande med UID 1 i Archive"):
        _run(None, mailbox="Archive")

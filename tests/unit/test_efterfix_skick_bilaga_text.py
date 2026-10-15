"""get_attachment(save=False) rensar textbilagor och märker innehållet som
opålitligt (granskning 3, injektion F4)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from protonmail_mcp.sanitize import UNTRUSTED_CONTENT_NOTICE
from protonmail_mcp.tools.attachments import get_attachment
from tests.feat_bilagor_support import attachment_env, base64_part, multipart, raw_message, text_part  # noqa: F401


def _run(raw, **kwargs):
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return asyncio.run(get_attachment(ctx, uid="1", mailbox="INBOX", index=0, **kwargs))


def _mail(content_type, data, name="a.txt"):
    return raw_message(multipart(text_part(), base64_part(content_type, f'; filename="{name}"', data)))


def test_text_attachment_is_sanitized(attachment_env):  # noqa: F811
    data = "Hej\U000E0049\U000E0047 v​ärlden".encode("utf-8")
    result = _run(_mail("text/plain; charset=utf-8", data), save=False)
    assert result["content"] == "Hej världen"
    assert result["sanitized"] == {"content": 3}
    assert result["untrusted_content_notice"] == UNTRUSTED_CONTENT_NOTICE
    # size och sha256 gäller bilagans bytes som de ligger i mejlet
    assert result["size"] == len(data)


def test_html_attachment_is_sanitized_but_stays_html(attachment_env):  # noqa: F811
    data = "<p>Hej‮</p>".encode("utf-8")
    result = _run(_mail("text/html; charset=utf-8", data, "a.html"), save=False)
    assert result["content"] == "<p>Hej</p>"
    assert result["sanitized"] == {"content": 1}


def test_base64_attachment_has_notice_but_no_sanitized(attachment_env):  # noqa: F811
    result = _run(_mail("application/octet-stream", b"\x00\x01"), save=False)
    assert result["encoding"] == "base64"
    assert result["untrusted_content_notice"] == UNTRUSTED_CONTENT_NOTICE
    assert "sanitized" not in result


def test_saved_attachment_has_no_content_fields(attachment_env):  # noqa: F811
    result = _run(_mail("text/plain; charset=utf-8", b"x"), save=True)
    assert "content" not in result and "sanitized" not in result


def test_docstring_no_longer_claims_filename_is_as_in_the_mail():
    doc = get_attachment.__doc__
    assert "(som i mejlet)" not in doc
    assert "untrusted_content_notice" in doc and "sanitized" in doc

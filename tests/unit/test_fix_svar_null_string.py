"""Valfria strängparametrar i send_email och reply_to_email json-tolkas inte.

MCP-SDK:ns pre_parse_json kör json.loads på strängvärden för parametrar vars
annotation inte är exakt `str`; för `str | None` blev strängen "null" None.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.server import mcp
from protonmail_mcp.tools import reply, send  # noqa: F401 — registrerar verktygen
from tests import sdk_support as sdk

RAW = (
    b"From: a@x.se\r\nTo: me@proton.me\r\nSubject: s\r\nMessage-ID: <m@x>\r\n"
    b"Content-Type: text/plain\r\n\r\nhej\r\n"
)


@pytest.fixture
def ctx():
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()
    app.imap.get_message.return_value = RAW
    app.smtp = AsyncMock()
    app.smtp.send_email.return_value = True
    return ctx


async def _run(ctx, tool, **args):
    await sdk.get_tool(mcp, tool).run(args, context=ctx)
    return ctx.request_context.lifespan_context.smtp.send_email.call_args.kwargs


@pytest.mark.parametrize("field", ["body_html", "reply_to"])
@pytest.mark.parametrize("value", ["null", "[1]", "true"])
async def test_send_email_keeps_json_looking_strings(ctx, field, value):
    kwargs = await _run(ctx, "send_email", to="b@x.se", subject="s", body="b", **{field: value})
    assert kwargs[field] == value


@pytest.mark.parametrize("field", ["body_html", "reply_to"])
async def test_send_email_explicit_null_is_none(ctx, field):
    kwargs = await _run(ctx, "send_email", to="b@x.se", subject="s", body="b", **{field: None})
    assert kwargs[field] is None


@pytest.mark.parametrize("value", ["null", "[1]"])
async def test_reply_body_html_keeps_json_looking_strings(ctx, value):
    kwargs = await _run(ctx, "reply_to_email", mailbox="INBOX", uid="1", body="b", body_html=value)
    assert kwargs["body_html"].startswith(value)


async def test_reply_body_html_explicit_null_is_none(ctx):
    kwargs = await _run(ctx, "reply_to_email", mailbox="INBOX", uid="1", body="b", body_html=None)
    assert kwargs["body_html"] is None


async def test_schemas_still_advertise_nullable_string():
    tools = {t.name: t for t in await mcp.list_tools()}
    for tool, field in [("send_email", "body_html"), ("send_email", "reply_to"), ("reply_to_email", "body_html")]:
        prop = sdk.wire(tools[tool])["inputSchema"]["properties"][field]
        assert prop["anyOf"] == [{"type": "string"}, {"type": "null"}]
        assert prop["default"] is None

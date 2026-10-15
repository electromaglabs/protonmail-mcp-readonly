"""BDD-tester för body_format/max_length i get_email (fix-verktyg, punkt 14)."""
import asyncio

from pytest_bdd import scenarios, given, when, then, parsers

from mcp.server.fastmcp.exceptions import ToolError

from protonmail_mcp.server import mcp
from protonmail_mcp.tools import messages  # noqa: F401 — registrerar verktygen

scenarios("fix_verktyg_body_format.feature")


def _call(mock_ctx, args):
    tool = mcp._tool_manager.get_tool("get_email")
    try:
        return {"result": asyncio.run(tool.run(args, context=mock_ctx)), "error": None}
    except ToolError as e:
        return {"result": None, "error": e}


@given(parsers.parse('att brevet med UID "{uid}" finns i INBOX'), target_fixture="uid")
def message_exists(mock_ctx, sample_raw_email, uid):
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = sample_raw_email
    return uid


@when(parsers.parse('jag hämtar brevet med body_format "{fmt}" och max_length {n:d}'), target_fixture="outcome")
def get_with_format_and_length(mock_ctx, uid, fmt, n):
    return _call(mock_ctx, {"uid": uid, "mailbox": "INBOX", "body_format": fmt, "max_length": n})


@when(parsers.parse('jag hämtar brevet med body_format "{fmt}"'), target_fixture="outcome")
def get_with_format(mock_ctx, uid, fmt):
    return _call(mock_ctx, {"uid": uid, "mailbox": "INBOX", "body_format": fmt})


@when(parsers.parse("jag hämtar brevet med max_length {n:d}"), target_fixture="outcome")
def get_with_length(mock_ctx, uid, n):
    return _call(mock_ctx, {"uid": uid, "mailbox": "INBOX", "max_length": n})


@then(parsers.parse('ska anropet avvisas med ett valideringsfel om "{field}"'))
def rejected(outcome, field):
    assert outcome["error"] is not None, f"förväntade fel, fick {outcome['result']}"
    msg = str(outcome["error"])
    assert "validation error" in msg
    assert f"\n{field}\n" in msg


@then(parsers.parse('ska brevet returneras med ämnesraden "{subject}"'))
def returned(outcome, subject):
    assert outcome["error"] is None, outcome["error"]
    assert outcome["result"]["subject"] == subject

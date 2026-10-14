"""BDD-tester: strängen "null" json-tolkas inte till None (fix-verktyg, punkt 16)."""
import asyncio

from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.server import mcp
from protonmail_mcp.tools import search  # noqa: F401 — registrerar verktygen

scenarios("fix_verktyg_null_string.feature")


@given("att jag är ansluten till brevlådan")
def connected(mock_ctx):
    mock_ctx.request_context.lifespan_context.imap.search_messages.return_value = {"messages": [], "total": 0, "has_more": False, "complete": True, "note": None}


@when(parsers.parse('jag söker i INBOX med {field} "{value}"'))
def search_with_string(mock_ctx, field, value):
    tool = mcp._tool_manager.get_tool("search_emails")
    asyncio.run(tool.run({"mailbox": "INBOX", field: value}, context=mock_ctx))


@when(parsers.parse("jag söker i INBOX med {field} satt till JSON-null"))
def search_with_null(mock_ctx, field):
    tool = mcp._tool_manager.get_tool("search_emails")
    asyncio.run(tool.run({"mailbox": "INBOX", field: None}, context=mock_ctx))


@then(parsers.parse('ska IMAP-sökningen få {field} "{value}"'))
def imap_got_string(mock_ctx, field, value):
    kwargs = mock_ctx.request_context.lifespan_context.imap.search_messages.call_args.kwargs
    assert kwargs[field] == value


@then(parsers.parse("ska IMAP-sökningen få {field} None"))
def imap_got_none(mock_ctx, field):
    kwargs = mock_ctx.request_context.lifespan_context.imap.search_messages.call_args.kwargs
    assert kwargs[field] is None

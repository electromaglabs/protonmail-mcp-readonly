"""BDD-tester för get_email/get_email_headers på obefintligt UID (fix-verktyg, punkt 13)."""
import asyncio

from pytest_bdd import scenarios, given, when, then, parsers

from tests.sdk_support import ToolError

from protonmail_mcp.server import mcp
from tests import sdk_support as sdk
from protonmail_mcp.tools import messages  # noqa: F401 — registrerar verktygen

scenarios("fix_verktyg_not_found.feature")


@given(parsers.parse('att mappen "{mailbox}" inte har något brev med UID "{uid}"'))
def no_such_message(mock_ctx, mailbox, uid):
    imap = mock_ctx.request_context.lifespan_context.imap
    imap.get_message.return_value = None
    imap.get_message_headers.return_value = None


@when(
    parsers.parse('jag anropar {tool_name} med uid "{uid}" i mappen "{mailbox}"'),
    target_fixture="outcome",
)
def call_tool(mock_ctx, tool_name, uid, mailbox):
    tool = sdk.get_tool(mcp, tool_name)
    try:
        return {"result": asyncio.run(tool.run({"uid": uid, "mailbox": mailbox}, context=mock_ctx)),
                "error": None}
    except ToolError as e:
        return {"result": None, "error": e}


@then(parsers.parse('ska anropet misslyckas med meddelandet "{message}"'))
def fails_with(outcome, message):
    assert outcome["error"] is not None, f"förväntade fel, fick {outcome['result']!r}"
    assert message in str(outcome["error"])

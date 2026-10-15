"""BDD: unflag_email tar bort mejlet ur Starred-vyn direkt (L1)."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.labels import unflag_email

from .conftest import run_tool, uid_list

scenarios("efterfix_live_stjarna.feature")


@when(parsers.parse('jag tar bort stjärnmärkningen på UID "{uid}" i "{mailbox}"'))
def do_unflag(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, unflag_email(mock_ctx, uid=uid, mailbox=mailbox))


@when(parsers.parse('jag tar bort stjärnmärkningen på UID-listan "{uids}" i "{mailbox}"'))
def do_unflag_list(mock_ctx, bridge, uids, mailbox):
    run_tool(bridge, unflag_email(mock_ctx, uid=uid_list(uids), mailbox=mailbox))

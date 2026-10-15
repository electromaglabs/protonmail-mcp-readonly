"""BDD: permanent radering när Bridge nekar men ändå raderar (L2), och föräldralösa utkast (L3)."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.manage import delete_email

from .conftest import run_tool, uid_list

scenarios("efterfix_live_radering.feature")


@when(parsers.parse('jag raderar UID-listan "{uids}" i "{mailbox}" permanent'))
def delete_list(mock_ctx, bridge, uids, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid_list(uids), mailbox=mailbox, permanent=True))


@when(parsers.parse('jag raderar mejlet med UID "{uid}" i "{mailbox}" permanent'))
def delete_one(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid, mailbox=mailbox, permanent=True))

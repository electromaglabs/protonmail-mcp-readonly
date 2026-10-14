"""BDD: delete_email flyttar till Trash; permanent radering bara uttryckligen och bara ett mejl."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.manage import delete_email

from .conftest import run_tool

scenarios("fix_flytta_delete.feature")


@when(parsers.parse('jag tar bort mejlet med UID "{uid}" i "{mailbox}"'))
def delete(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid, mailbox=mailbox))


@when(parsers.parse('jag raderar mejlet med UID "{uid}" i "{mailbox}" permanent'))
def delete_permanently(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid, mailbox=mailbox, permanent=True))

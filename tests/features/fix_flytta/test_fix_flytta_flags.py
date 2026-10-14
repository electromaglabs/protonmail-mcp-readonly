"""BDD: mark_email_read/unread kontrollerar att UID:t finns och vad Bridge svarar."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.manage import mark_email_read, mark_email_unread

from .conftest import run_tool

scenarios("fix_flytta_flags.feature")


@when(parsers.parse('jag markerar mejlet med UID "{uid}" i "{mailbox}" som läst'))
def mark_read(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, mark_email_read(mock_ctx, uid=uid, mailbox=mailbox))


@when(parsers.parse('jag markerar mejlet med UID "{uid}" i "{mailbox}" som oläst'))
def mark_unread(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, mark_email_unread(mock_ctx, uid=uid, mailbox=mailbox))

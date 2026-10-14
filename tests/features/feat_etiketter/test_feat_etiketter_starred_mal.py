"""BDD: move_email till Starred avvisas och hänvisar till flag_email."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.manage import move_email

from .conftest import run_tool, uid_list

scenarios("feat_etiketter_starred_mal.feature")


@when(parsers.parse('jag flyttar mejlet med UID "{uid}" från "{mailbox}" till "{target}"'))
def move_one(mock_ctx, bridge, uid, mailbox, target):
    run_tool(bridge, move_email(mock_ctx, uid=uid, target_mailbox=target, mailbox=mailbox))


@when(parsers.parse('jag flyttar UID-listan "{uids}" från "{mailbox}" till "{target}"'))
def move_many(mock_ctx, bridge, uids, mailbox, target):
    run_tool(bridge, move_email(mock_ctx, uid=uid_list(uids), target_mailbox=target, mailbox=mailbox))

"""BDD: move_email avvisar Starred som mål (S2)."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.manage import move_email

from .conftest import run_tool

scenarios("efterfix_imap_starred_mal.feature")


@when(parsers.parse('jag flyttar mejlet med UID "{uid}" från "{source}" till "{target}"'))
def move(mock_ctx, bridge, uid, source, target):
    run_tool(bridge, move_email(mock_ctx, uid=uid, target_mailbox=target, mailbox=source))

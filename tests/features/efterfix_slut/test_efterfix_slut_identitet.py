"""BDD: identiteten X-Pm-Internal-Id i move/delete (L7-kontrollen) och remove_label (G5K-2)."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.labels import remove_label
from protonmail_mcp.tools.manage import delete_email

from .conftest import run_tool, uid_list

scenarios("efterfix_slut_identitet.feature")


@when(parsers.parse('jag tar bort UID-listan "{uids}" i "{mailbox}"'))
def delete_list(mock_ctx, bridge, uids, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid_list(uids), mailbox=mailbox))


@when(parsers.parse('jag tar bort mejlet med UID "{uid}" i "{mailbox}"'))
def delete_one(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid, mailbox=mailbox))


@when(parsers.parse('jag tar bort etiketten "{label}" från UID "{uid}" i "{mailbox}"'))
def unlabel(mock_ctx, bridge, label, uid, mailbox):
    bridge.add_label(f"Labels/{label}")
    run_tool(bridge, remove_label(mock_ctx, uid=uid, mailbox=mailbox, label=label))

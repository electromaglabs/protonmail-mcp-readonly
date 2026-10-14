"""BDD: verktygen tar en lista med upp till 100 UID:n och svarar per UID."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.labels import add_label, flag_email, remove_label
from protonmail_mcp.tools.manage import delete_email, mark_email_read, move_email

from .conftest import run_tool, uid_list

scenarios("feat_etiketter_bulk.feature")


@when(parsers.parse('jag markerar UID-listan "{uids}" i "{mailbox}" som lästa'))
def bulk_read(mock_ctx, bridge, uids, mailbox):
    run_tool(bridge, mark_email_read(mock_ctx, uid=uid_list(uids), mailbox=mailbox))


@when(parsers.parse('jag markerar {count:d} UID:n i "{mailbox}" som lästa'))
def bulk_read_many(mock_ctx, bridge, count, mailbox):
    uids = [str(n) for n in range(1, count + 1)]
    run_tool(bridge, mark_email_read(mock_ctx, uid=uids, mailbox=mailbox))


@when(parsers.parse('jag flyttar UID-listan "{uids}" från "{mailbox}" till "{target}"'))
def bulk_move(mock_ctx, bridge, uids, mailbox, target):
    run_tool(bridge, move_email(mock_ctx, uid=uid_list(uids), target_mailbox=target, mailbox=mailbox))


@when(parsers.parse('jag tar bort UID-listan "{uids}" i "{mailbox}"'))
def bulk_delete(mock_ctx, bridge, uids, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid_list(uids), mailbox=mailbox))


@when(parsers.parse('jag raderar UID-listan "{uids}" i "{mailbox}" permanent'))
def bulk_delete_permanent(mock_ctx, bridge, uids, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid_list(uids), mailbox=mailbox, permanent=True))


@when(parsers.parse('jag lägger till etiketten "{label}" på UID-listan "{uids}" i "{mailbox}"'))
def bulk_add_label(mock_ctx, bridge, label, uids, mailbox):
    run_tool(bridge, add_label(mock_ctx, uid=uid_list(uids), mailbox=mailbox, label=label))


@when(parsers.parse('jag tar bort etiketten "{label}" från UID-listan "{uids}" i "{mailbox}"'))
def bulk_remove_label(mock_ctx, bridge, label, uids, mailbox):
    run_tool(bridge, remove_label(mock_ctx, uid=uid_list(uids), mailbox=mailbox, label=label))


@when(parsers.parse('jag stjärnmärker UID-listan "{uids}" i "{mailbox}"'))
def bulk_flag(mock_ctx, bridge, uids, mailbox):
    run_tool(bridge, flag_email(mock_ctx, uid=uid_list(uids), mailbox=mailbox))

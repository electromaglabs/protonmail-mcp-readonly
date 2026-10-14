"""BDD: remove_label tar bort bara etiketten, med UID EXPUNGE i etikettens vy."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.labels import remove_label

from .conftest import run_tool

scenarios("feat_etiketter_remove_label.feature")


@when(parsers.parse('jag tar bort etiketten "{label}" från UID "{uid}" i "{mailbox}"'))
def do_remove_label(mock_ctx, bridge, label, uid, mailbox):
    run_tool(bridge, remove_label(mock_ctx, uid=uid, mailbox=mailbox, label=label))

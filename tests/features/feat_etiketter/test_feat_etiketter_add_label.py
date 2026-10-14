"""BDD: add_label lägger till en etikett med UID COPY och mejlet ligger kvar."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.labels import add_label

from .conftest import run_tool

scenarios("feat_etiketter_add_label.feature")


@when(parsers.parse('jag lägger till etiketten "{label}" på UID "{uid}" i "{mailbox}"'))
def do_add_label(mock_ctx, bridge, label, uid, mailbox):
    run_tool(bridge, add_label(mock_ctx, uid=uid, mailbox=mailbox, label=label))

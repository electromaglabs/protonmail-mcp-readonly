"""BDD: flag_email/unflag_email sätter och tar bort \\Flagged (Starred i Proton)."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.labels import flag_email, unflag_email

from .conftest import run_tool

scenarios("feat_etiketter_flag.feature")


@when(parsers.parse('jag stjärnmärker UID "{uid}" i "{mailbox}"'))
def do_flag(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, flag_email(mock_ctx, uid=uid, mailbox=mailbox))


@when(parsers.parse('jag tar bort stjärnmärkningen på UID "{uid}" i "{mailbox}"'))
def do_unflag(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, unflag_email(mock_ctx, uid=uid, mailbox=mailbox))

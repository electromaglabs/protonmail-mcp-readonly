"""BDD: NO/BAD på LIST och FETCH ger fel med Bridges text (F3/K3)."""
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.mailboxes import list_mailboxes
from protonmail_mcp.tools.messages import list_emails

from .conftest import install_bodies, run_tool

scenarios("efterfix_imap_serverfel.feature")


@given(parsers.parse('att Bridge nekar {command} med "{text}"'))
def bridge_refuses(bridge, command, text):
    install_bodies(bridge)
    bridge.refuse[command] = text


@when("jag listar mapparna")
def list_folders(mock_ctx, bridge):
    run_tool(bridge, list_mailboxes(mock_ctx))


@when(parsers.parse('jag listar mejlen i "{mailbox}"'))
def list_mails(mock_ctx, bridge, mailbox):
    run_tool(bridge, list_emails(mock_ctx, mailbox=mailbox))


@then("ska felet inte påstå att mejlet saknas")
def not_claimed_missing(bridge):
    assert "Inget meddelande" not in bridge.errors[0], bridge.errors[0]

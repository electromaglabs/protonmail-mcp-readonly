"""BDD: \\Noselect-behållare ger ett tydligt fel (F4/K8, N9 del 2)."""
from pytest_bdd import given, parsers, scenarios, when

from protonmail_mcp.tools.messages import list_emails
from protonmail_mcp.tools.search import search_emails

from .conftest import install_bodies, run_tool

scenarios("efterfix_imap_behallare.feature")


@given(parsers.parse('att Bridge visar "{name}" som behållare'))
def container(bridge, name):
    install_bodies(bridge)
    # Som Bridge: LIST visar \Noselect, men SELECT och STATUS svarar OK med 0 mejl
    bridge.containers.add(name)
    bridge.mailboxes[name] = set()


@when(parsers.parse('jag listar mejlen i "{mailbox}"'))
def list_mails(mock_ctx, bridge, mailbox):
    install_bodies(bridge)
    run_tool(bridge, list_emails(mock_ctx, mailbox=mailbox))


@when(parsers.parse('jag söker efter olästa mejl i "{mailbox}"'))
def search_unseen(mock_ctx, bridge, mailbox):
    run_tool(bridge, search_emails(mock_ctx, mailbox=mailbox, unseen=True))

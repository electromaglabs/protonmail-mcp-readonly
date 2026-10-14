"""BDD: STATUS-svarets antal tolkas bara ur parentesen, inte ur mappnamnet (K1/F1)."""
from pytest_bdd import parsers, scenarios, then, when

from protonmail_mcp.tools.folders import delete_folder

from .conftest import run_tool

scenarios("efterfix_imap_status_namn.feature")


@when(parsers.parse('jag tar bort mappen "{name}"'))
def delete(mock_ctx, bridge, name):
    run_tool(bridge, delete_folder(mock_ctx, name=name))


@then(parsers.parse("ska statusen vara {messages:d} mejl och {unseen:d} olästa"))
def status_is(bridge, messages, unseen):
    assert bridge.errors == []
    assert bridge.result == {"messages": messages, "unseen": unseen}

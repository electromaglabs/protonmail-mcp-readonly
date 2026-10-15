"""BDD: serverinstruktionerna (MCPServer instructions) når klienten (llm-kontrakt)."""
from pytest_bdd import parsers, scenarios, then, when

from protonmail_mcp.server import mcp
from tests import sdk_support as sdk

scenarios("llm_kontrakt_instruktioner.feature")


@when("en klient ansluter till servern", target_fixture="instructions")
def connect():
    # Det klienten får i initialize-svaret
    return sdk.init_options(mcp)["instructions"]


@then("ska servern skicka instruktioner")
def has_instructions(instructions):
    assert instructions and instructions.strip()


@then(parsers.parse('ska instruktionerna nämna "{text}"'))
def mentions(instructions, text):
    assert text in instructions

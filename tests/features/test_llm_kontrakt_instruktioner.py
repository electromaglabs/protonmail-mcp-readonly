"""BDD: serverinstruktionerna (FastMCP instructions) når klienten (llm-kontrakt)."""
import asyncio

from pytest_bdd import parsers, scenarios, then, when

from protonmail_mcp.server import mcp

scenarios("llm_kontrakt_instruktioner.feature")


@when("en klient ansluter till servern", target_fixture="instructions")
def connect():
    # Det klienten får i initialize-svaret
    return mcp._mcp_server.create_initialization_options().instructions


@then("ska servern skicka instruktioner")
def has_instructions(instructions):
    assert instructions and instructions.strip()


@then(parsers.parse('ska instruktionerna nämna "{text}"'))
def mentions(instructions, text):
    assert text in instructions

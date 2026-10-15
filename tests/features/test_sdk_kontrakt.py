"""BDD: MCP-kontraktet jämfört med facitfilen (karaktärisering inför SDK-byte)."""
import asyncio

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests import sdk_kontrakt_support as kontrakt

scenarios("sdk_kontrakt.feature")


@pytest.fixture
def state():
    return {}


@when("en MCP-klient ansluter och listar verktyg, resurser, resursmallar och promptar")
def connect_and_list(monkeypatch, state):
    state["listing"] = asyncio.run(kontrakt.listing(monkeypatch))


@then("ska serverInfo, instruktionerna och förmågorna vara som i facitfilen")
def server_matches(state):
    kontrakt.check("server", state["listing"]["server"])


@then("ska verktygens namn, titlar, scheman och annoteringar vara som i facitfilen")
def tools_match(state):
    assert len(state["listing"]["tools"]) == 29
    kontrakt.check("tools", state["listing"]["tools"])


@then("ska resurserna, resursmallarna och promptarna vara som i facitfilen")
def resources_match(state):
    for section in ("resources", "resourceTemplates", "prompts"):
        kontrakt.check(section, state["listing"][section])


@when("en MCP-klient gör anrop som ger fel")
def make_errors(monkeypatch, state):
    state["errors"] = asyncio.run(kontrakt.errors(monkeypatch))


@then("ska felen vara som i facitfilen")
def errors_match(state):
    kontrakt.check("errors", state["errors"])


@then("ska serverns egna felmeddelanden nå klienten i sin helhet")
def own_errors_intact(state):
    for key, phrase in kontrakt.OWN_ERRORS.items():
        assert phrase in kontrakt.error_text(state["errors"][key]), key


@then("ska inget resursfel ha ett engelskt prefix från SDK:n")
def no_sdk_prefix(state):
    for key, result in state["errors"].items():
        if key.startswith("resurs_"):
            assert not kontrakt.error_text(result).startswith(kontrakt.SDK_PREFIXES), key


@given("servern är skrivskyddad")
def read_only(state):
    state["read_only"] = True


@when(parsers.parse('en MCP-klient anropar "{tool}"'))
def call_tool(monkeypatch, state, tool):
    args = {"to": "anna@exempel.se", "subject": "Hej", "body": "Hej Anna"}
    state["result"] = asyncio.run(kontrakt.policy_refusal(monkeypatch, tool, args))


@then(parsers.parse('ska anropet ge ett fel som nämner "{text}"'))
def refused(state, text):
    result = state["result"]
    message = result.get("text") or result.get("mcp_error", "")
    assert result.get("isError") or "mcp_error" in result
    assert text in message, message


@then(parsers.parse('ska felet inte börja med "{prefix}"'))
def no_prefix(state, prefix):
    result = state["result"]
    assert not (result.get("text") or result.get("mcp_error", "")).startswith(prefix)

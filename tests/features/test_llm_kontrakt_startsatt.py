"""BDD: verktygen registreras både via entrypointen och med python -m (llm-kontrakt)."""
import runpy
import warnings

import pytest
from pytest_bdd import parsers, scenarios, then, when

from protonmail_mcp import server
from tests import sdk_support as sdk

scenarios("llm_kontrakt_startsatt.feature")


@pytest.fixture
def started(monkeypatch):
    """Fångar servern som run() anropas på, i stället för att starta stdio."""
    return sdk.patch_run(monkeypatch)


def _names(mcp_server: sdk.MCPServer) -> set[str]:
    return {t.name for t in sdk.list_tools(mcp_server)}


@when(parsers.parse('servern startas med "python -m protonmail_mcp.server"'))
def start_as_module(started):
    with warnings.catch_warnings():
        # runpy varnar för att modulen redan är importerad — det är avsikten här
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("protonmail_mcp.server", run_name="__main__")


@when("servern startas med kommandot protonmail-mcp")
def start_as_entrypoint(started):
    server.main()


@then("ska den startade servern ha samma verktyg som kommandot protonmail-mcp")
def same_tools_as_entrypoint(started):
    server.register_tools()
    assert _names(started["server"]) == _names(server.mcp)


@then(parsers.parse("ska den startade servern ha {count:d} verktyg"))
def has_tools(started, count):
    assert len(_names(started["server"])) == count

"""BDD: python -m protonmail_mcp startar samma server (efterfix-resurser)."""
import runpy
import warnings

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import NotificationOptions
from pytest_bdd import parsers, scenarios, then, when

from protonmail_mcp import server

scenarios("efterfix_resurser_startsatt.feature")


@pytest.fixture
def started(monkeypatch):
    """Fångar servern som run() anropas på, i stället för att starta stdio."""
    captured = {}
    monkeypatch.setattr(FastMCP, "run", lambda self, *a, **k: captured.setdefault("server", self))
    return captured


@when('servern startas med "python -m protonmail_mcp"')
def start_package(started):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("protonmail_mcp", run_name="__main__", alter_sys=True)
    assert "server" in started, "python -m protonmail_mcp startade ingen server"


def _tool_names(srv):
    return {t.name for t in srv._tool_manager.list_tools()}


@then("ska den startade servern ha samma verktyg som med kommandot protonmail-mcp")
def same_tools(started):
    server.register_tools()
    assert started["server"] is server.mcp
    assert _tool_names(started["server"]) == _tool_names(server.mcp)
    assert len(_tool_names(started["server"])) > 0


@then('ska den startade servern ha resursen "mailboxes://" och prenumerationer på resurser')
def resources_and_subscribe(started):
    srv = started["server"]
    assert "mailboxes://" in [str(r.uri) for r in srv._resource_manager.list_resources()]
    caps = srv._mcp_server.get_capabilities(NotificationOptions(), {})
    assert caps.resources.subscribe is True


@then(parsers.parse('ska den startade servern ha promptarna "{names}"'))
def has_prompts(started, names):
    listed = {p.name for p in started["server"]._prompt_manager.list_prompts()}
    assert {n.strip() for n in names.split(",")} <= listed

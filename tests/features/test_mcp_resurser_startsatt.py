"""BDD: resurser, promptar och prenumerationer oavsett startsätt (mcp-resurser)."""
import runpy
import warnings

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import NotificationOptions
from pytest_bdd import parsers, scenarios, then, when

from protonmail_mcp import server

scenarios("mcp_resurser_startsatt.feature")


@pytest.fixture
def started(monkeypatch):
    """Fångar servern som run() anropas på, i stället för att starta stdio."""
    captured = {}
    monkeypatch.setattr(FastMCP, "run", lambda self, *a, **k: captured.setdefault("server", self))
    return captured


@when(parsers.parse("servern startas med {how}"))
def start(started, how):
    if how == '"python -m protonmail_mcp.server"':
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            runpy.run_module("protonmail_mcp.server", run_name="__main__")
    else:
        assert how == "kommandot protonmail-mcp"
        server.main()


@then(parsers.parse('ska den startade servern ha resursen "{uri}"'))
def has_resource(started, uri):
    assert uri in [str(r.uri) for r in started["server"]._resource_manager.list_resources()]


@then(parsers.parse('ska den startade servern ha resursmallarna "{first}" och "{second}"'))
def has_templates(started, first, second):
    templates = [t.uri_template for t in started["server"]._resource_manager.list_templates()]
    assert first in templates and second in templates


@then(parsers.parse('ska den startade servern ha promptarna "{names}"'))
def has_prompts(started, names):
    listed = {p.name for p in started["server"]._prompt_manager.list_prompts()}
    assert {n.strip() for n in names.split(",")} <= listed


@then("ska den startade servern annonsera prenumerationer på resurser")
def announces_subscribe(started):
    caps = started["server"]._mcp_server.get_capabilities(NotificationOptions(), {})
    assert caps.resources.subscribe is True

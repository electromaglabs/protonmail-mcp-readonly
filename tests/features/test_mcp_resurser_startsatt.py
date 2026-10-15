"""BDD: resurser, promptar och prenumerationer oavsett startsätt (mcp-resurser)."""
import runpy
import warnings

import pytest
from pytest_bdd import parsers, scenarios, then, when

from protonmail_mcp import server
from tests import sdk_support as sdk

scenarios("mcp_resurser_startsatt.feature")


@pytest.fixture
def started(monkeypatch):
    """Fångar servern som run() anropas på, i stället för att starta stdio."""
    return sdk.patch_run(monkeypatch)


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
    assert uri in [str(r.uri) for r in sdk.list_resources(started["server"])]


@then(parsers.parse('ska den startade servern ha resursmallarna "{first}" och "{second}"'))
def has_templates(started, first, second):
    templates = [t.uri_template for t in sdk.list_templates(started["server"])]
    assert first in templates and second in templates


@then(parsers.parse('ska den startade servern ha promptarna "{names}"'))
def has_prompts(started, names):
    listed = {p.name for p in sdk.list_prompts(started["server"])}
    assert {n.strip() for n in names.split(",")} <= listed


@then("ska den startade servern annonsera prenumerationer på resurser")
def announces_subscribe(started):
    assert sdk.capabilities(started["server"])["resources"]["subscribe"] is True

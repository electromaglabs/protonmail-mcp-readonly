"""BDD: verktygsannoteringar som klienten ser dem i list_tools (llm-kontrakt)."""
import asyncio

import pytest
from pytest_bdd import parsers, scenarios, then, when

from tests import sdk_support as sdk
from tests.llm_kontrakt_support import client_session

scenarios("llm_kontrakt_annoteringar.feature")


@pytest.fixture
def listed(monkeypatch):
    async def run():
        async with client_session(monkeypatch) as session:
            return (await session.list_tools()).tools

    return run


@when("klienten listar verktygen", target_fixture="tools")
def list_tools(listed):
    return {t.name: t for t in asyncio.run(listed())}


def _hint(tools, name, hint):
    """En annotering i wire-format (camelCase), None om den saknas."""
    return sdk.wire(tools[name].annotations).get(hint)


@then("ska varje verktyg ha en titel")
def every_tool_has_title(tools):
    for tool in tools.values():
        assert tool.title, tool.name
        assert tool.annotations is not None and tool.annotations.title == tool.title, tool.name


@then("ska varje verktyg ha annoteringar för läs-endast, destruktiv, idempotent och öppen värld")
def every_tool_has_hints(tools):
    for tool in tools.values():
        ann = sdk.wire(tool.annotations)
        hints = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
        for hint in (ann.get(h) for h in hints):
            assert isinstance(hint, bool), tool.name


@then(parsers.parse("ska {name:w} vara läs-endast"))
def read_only(tools, name):
    assert _hint(tools, name, "readOnlyHint") is True
    assert _hint(tools, name, "destructiveHint") is False


@then(parsers.parse("ska {name:w} inte nå omvärlden"))
def closed_world(tools, name):
    assert _hint(tools, name, "openWorldHint") is False


@then(parsers.parse("ska {name:w} nå omvärlden"))
def open_world(tools, name):
    assert _hint(tools, name, "openWorldHint") is True


@then(parsers.parse("ska {name:w} inte vara destruktivt"))
def not_destructive(tools, name):
    assert _hint(tools, name, "readOnlyHint") is False
    assert _hint(tools, name, "destructiveHint") is False


@then(parsers.parse("ska {name:w} vara destruktivt"))
def destructive(tools, name):
    assert _hint(tools, name, "readOnlyHint") is False
    assert _hint(tools, name, "destructiveHint") is True


@then(parsers.parse("ska {name:w} vara idempotent"))
def idempotent(tools, name):
    assert _hint(tools, name, "idempotentHint") is True

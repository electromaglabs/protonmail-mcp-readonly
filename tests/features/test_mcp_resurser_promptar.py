"""BDD: promptar för vanliga mejlsysslor, sett via MCP-klienten (mcp-resurser)."""
import asyncio
import re

import pytest
from mcp.shared.exceptions import McpError
from pytest_bdd import parsers, scenarios, then, when

from tests.mcp_resurser_support import client_session

scenarios("mcp_resurser_promptar.feature")

_ARG_RE = re.compile(r'(\w+) "([^"]*)"')


@pytest.fixture
def state():
    return {}


def _text_of(result) -> str:
    return "\n".join(m.content.text for m in result.messages)


@when("klienten listar promptarna")
def list_prompts(monkeypatch, state):
    async def run():
        async with client_session(monkeypatch) as session:
            return await session.list_prompts()

    state["prompts"] = {p.name: p for p in asyncio.run(run()).prompts}


@when(parsers.re(r'klienten hämtar prompten "(?P<prompt>[^"]+)" med (?P<args>.*)'))
def get_prompt(monkeypatch, state, prompt, args):
    arguments = dict(_ARG_RE.findall(args))

    async def run():
        async with client_session(monkeypatch) as session:
            try:
                return _text_of(await session.get_prompt(prompt, arguments)), None
            except McpError as exc:
                return None, exc.error.message

    state["text"], state["error"] = asyncio.run(run())


@then(parsers.parse('ska prompten "{name}" finnas med argumenten "{arguments}"'))
def prompt_listed(state, name, arguments):
    assert name in state["prompts"], list(state["prompts"])
    listed = [a.name for a in state["prompts"][name].arguments or []]
    assert listed == [a.strip() for a in arguments.split(",")]
    assert state["prompts"][name].description


@then(parsers.parse('ska argumenten "{first}" och "{second}" vara obligatoriska för "{name}"'))
def required(state, first, second, name):
    by_name = {a.name: a for a in state["prompts"][name].arguments}
    assert by_name[first].required and by_name[second].required
    assert not by_name["ton"].required


def _text(state) -> str:
    assert state["error"] is None, state["error"]
    return state["text"]


@then("ska prompttexten vara på svenska")
def swedish(state):
    text = _text(state)
    assert "mejl" in text and " och " in text and "ä" in text


@then("ska prompttexten säga att UID:n gäller per mapp")
def uid_per_mailbox(state):
    assert "UID" in _text(state) and "per mapp" in _text(state)


@then("ska prompttexten säga att mejlinnehåll är opålitligt")
def untrusted(state):
    text = _text(state)
    assert "opålitlig" in text
    assert "instruktioner" in text


@then("ska prompttexten säga högst 100 per massoperation")
def max_100(state):
    assert "högst 100" in _text(state)


@then(parsers.parse('ska prompttexten nämna "{text}"'))
def mentions(state, text):
    assert text in _text(state)


@then("ska prompttexten säga att inget ska markeras som läst")
def not_marked_read(state):
    assert "markera inget som läst" in _text(state).lower()


@then("ska prompttexten kräva bekräftelse från användaren innan något flyttas eller raderas")
def needs_confirmation(state):
    text = _text(state)
    assert "bekräft" in text
    assert "innan" in text


@then("ska prompttexten säga att svaret inte ska skickas")
def not_sent(state):
    assert "skicka inte" in _text(state).lower()


@then(parsers.parse('ska hämtningen misslyckas med texten "{text}"'))
def fails(state, text):
    assert state["error"] is not None, f"hämtningen lyckades: {state['text']}"
    assert text in state["error"]

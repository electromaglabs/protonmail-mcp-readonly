"""BDD-steg för efterfix_skick_losenord.feature."""
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import config
from protonmail_mcp.tools import _errors

scenarios("efterfix_skick_losenord.feature")


@pytest.fixture
def pw_state():
    return {}


@given(parsers.parse('Bridge-lösenordet är "{password}"'))
def bridge_password(monkeypatch, pw_state, password):
    pw_state["password"] = password
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(password=password))


@when(parsers.parse("ett verktyg får ett anslutningsfel vars text innehåller lösenordet {form}"))
def connection_error(pw_state, form):
    pw = pw_state["password"]
    if form == "URL-kodat":
        text = f"login failed for imaps://me:{quote(pw, safe='')}@127.0.0.1"
    elif form == "med hopslagna blanksteg":
        text = f"login failed: {pw}"  # _detail slår ihop blankstegen
    else:
        text = "x" * (_errors._MAX_DETAIL_CHARS - 12) + " " + pw  # kapas efter "hemligt-los"
    pw_state["message"] = _errors.describe_error(ConnectionError(text), tool_name="list_emails", open_world=False)


@then("ska felet till modellen inte innehålla någon del av lösenordet")
def no_password(pw_state):
    message = pw_state["message"]
    assert "hemligt" not in message
    assert "lösen" not in message and "l%C3%B6sen" not in message

"""BDD-steg för efterfix_skick_trasig_adress.feature (gemensamma steg i conftest.py)."""
import logging

import pytest
from pytest_bdd import parsers, scenarios, then, when

from tests.llm_skick_support import call_tool, make_app, record_smtp

from .conftest import _run, _settings

scenarios("efterfix_skick_trasig_adress.feature")


@pytest.fixture(autouse=True)
def _all_logs(caplog):
    caplog.set_level(logging.DEBUG)


def _call(state, tool, args):
    settings = _settings(state)
    app = make_app(settings, state["spy"])
    with record_smtp(state["spy"]) as captured:
        state["captured"] = captured
        _run(state, lambda: call_tool(tool, args, app, settings))


@when(parsers.parse("""LLM:en skickar ett mejl till "{to}" med hemlig kopia '{bcc}'"""))
def llm_sends(state, to, bcc):
    _call(state, "send_email", {"to": to, "bcc": bcc, "subject": "Hej", "body": "Hej"})


@when(parsers.parse("""LLM:en skapar ett utkast till "{to}" med hemlig kopia '{bcc}'"""))
def llm_drafts(state, to, bcc):
    _call(state, "create_draft", {"to": to, "bcc": bcc, "subject": "Hej", "body": "Hej"})


@then("ska felet inte vara ett oväntat fel")
def not_unexpected(state):
    assert "Oväntat fel" not in str(state["error"])


@then(parsers.parse('ska serverns logg inte innehålla "{text}"'))
def log_lacks(caplog, text):
    # pytest-bdd loggar själv stegtexten på DEBUG; bara serverns loggar räknas
    server_log = "\n".join(
        f"{r.getMessage()}\n{r.exc_text or ''}" for r in caplog.records if not r.name.startswith("pytest_bdd")
    )
    assert server_log, "inget loggades alls — fångas loggarna?"
    assert text not in server_log

"""BDD-steg för llm_skick_granser.feature (gemensamma steg i conftest.py).

Samma SMTPClient används genom hela scenariot (räknaren ligger i minnet),
med en klocka som scenariot styr.
"""
import pytest
from pytest_bdd import parsers, scenarios, then, when

from protonmail_mcp.smtp_client import SMTPClient
from tests.llm_skick_support import record_smtp

from .conftest import _run, _settings

scenarios("llm_skick_granser.feature")


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


def _client(state, clock):
    if "smtp" not in state:
        state["smtp"] = SMTPClient(_settings(state))
        state["smtp"]._clock = clock
        state["sent"] = []
    return state["smtp"]


def _send(state, clock, to):
    smtp = _client(state, clock)
    state["error"] = None
    with record_smtp(state["spy"]) as captured:
        state["captured"] = captured
        _run(state, lambda: smtp.send_email(to=to, subject="Hej", body="Hej"))
    state["sent"] += captured.sent


@when(parsers.parse("koden skickar ett mejl till {count:d} olika mottagare"))
def send_to_many(state, clock, count):
    _send(state, clock, [f"m{i}@exempel.se" for i in range(count)])


@when(parsers.parse("koden skickar {count:d} mejl i rad"))
def send_many(state, clock, count):
    for _ in range(count):
        _send(state, clock, "anna@exempel.se")
        assert state["error"] is None, repr(state["error"])


@when(parsers.parse('koden skickar ett mejl till "{to}"'))
def send_one(state, clock, to):
    _send(state, clock, to)


@when(parsers.parse("det går {minutes:d} minuter"))
def time_passes(clock, minutes):
    clock.now += minutes * 60


@then(parsers.parse("ska bara {count:d} mejl ha skickats"))
def sent_count(state, count):
    assert len(state["sent"]) == count

"""BDD: en riktig session glöms när den stängs, före någon notis (efterfix-resurser, R4-4).

Skyddar beroendet av mcp:s privata BaseSession._exit_stack: om kroken inte
fäster på en riktig ServerSession faller scenariot, eftersom registret då
fortfarande har sessionen kvar (den städas annars bort först när en notis
till den misslyckas).
"""
import asyncio

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import subscriptions
from tests.efterfix_resurser_support import Collector, client_session

scenarios("efterfix_resurser_nedkoppling.feature")


@pytest.fixture(autouse=True)
def _empty_registry():
    subscriptions.registry.clear()
    yield
    subscriptions.registry.clear()


@pytest.fixture
def state(monkeypatch):
    sent = []
    original = subscriptions._send

    async def counting_send(session, uri):
        sent.append(uri)
        await original(session, uri)

    monkeypatch.setattr(subscriptions, "_send", counting_send)
    return {"uris": [], "sent": sent}


@given(parsers.parse('att en riktig klientsession prenumererar på "{first}" och "{second}"'))
def subscribes(state, first, second):
    state["uris"] = [first, second]


@when("klienten kopplar ner")
def disconnects(monkeypatch, state):
    async def run():
        async with client_session(monkeypatch, message_handler=Collector()) as session:
            for uri in state["uris"]:
                await session.subscribe_resource(uri)
            state["during"] = subscriptions.registry.sessions()
        # Ingen notis, ingen ping: bara att sessionen stängts
        state["after"] = subscriptions.registry.sessions()
        state["hooked_after"] = set(subscriptions.registry._hooked)

    asyncio.run(run())


@then("ska ingen session finnas kvar i prenumerationsregistret")
def registry_empty(state):
    assert len(state["during"]) == 1, "prenumerationen registrerades inte"
    assert state["after"] == [], "sessionen glömdes inte när den stängdes (fäster kroken på _exit_stack?)"
    assert state["hooked_after"] == set()


@then("ska ingen notis ha skickats")
def nothing_sent(state):
    assert state["sent"] == []

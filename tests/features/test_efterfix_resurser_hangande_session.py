"""BDD: en hängande session glöms efter N tidsgränser i rad (efterfix-resurser, R4-3)."""
import asyncio
import logging

import anyio
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import resources, subscriptions
from tests import sdk_support as sdk
from tests.efterfix_resurser_support import Collector, client_session

scenarios("efterfix_resurser_hangande_session.feature")

TIMEOUT = 0.2


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    subscriptions.registry.clear()
    monkeypatch.setattr(subscriptions, "SEND_TIMEOUT_SECONDS", TIMEOUT)
    yield
    subscriptions.registry.clear()


@pytest.fixture
def state():
    return {}


class _Scripted:
    """Session vars notiser tar för lång tid enligt ett schema (True = för långsam)."""

    def __init__(self, script):
        self.script = list(script)
        self.sent = []

    async def send_resource_updated(self, uri):
        if self.script.pop(0):
            await anyio.sleep(TIMEOUT * 5)
        self.sent.append(str(uri))


@given(parsers.parse('att en session som slutat läsa och en session som läser prenumererar på mappresursen för "{mailbox}"'))
def slow_and_fast(state, mailbox):
    state["mailbox"] = mailbox


@when(parsers.parse('servern meddelar att mappresursen för "{mailbox}" har ändrats tills den hängande sessionen nått tre tidsgränser i rad'))
def notify_until_forgotten(monkeypatch, state, caplog, mailbox):
    uri = resources.mailbox_uri(mailbox)
    fast = Collector()
    release = anyio.Event()

    async def stuck(message):
        if sdk.resource_updated_uri(message) is not None:
            await release.wait()

    async def run():
        async with client_session(monkeypatch, message_handler=stuck) as slow_client, \
                client_session(monkeypatch, message_handler=fast) as fast_client:
            await slow_client.subscribe_resource(uri)
            (slow_session,) = subscriptions.registry.sessions()
            await fast_client.subscribe_resource(uri)
            sent = 0
            # Minnesströmmen buffrar några notiser innan sändningen börjar vänta
            with caplog.at_level(logging.INFO, logger="protonmail_mcp.subscriptions"):
                while slow_session in subscriptions.registry.sessions() and sent < 20:
                    await subscriptions.notify_resource_updated(uri)
                    sent += 1
            await fast_client.send_ping()
            state["sent"] = sent
            state["slow"] = slow_session
            state["left"] = subscriptions.registry.sessions()
            state["fast_received"] = list(fast.uris)
            release.set()

    asyncio.run(run())
    state["log"] = caplog.text


@given(parsers.parse('att en session prenumererar på mappresursen för "{mailbox}"'))
def one_session(state, mailbox):
    state["mailbox"] = mailbox


@given("att notisen till den hinner ta för lång tid två gånger, sedan lyckas, och sedan tar för lång tid två gånger till")
def scripted(state):
    state["session"] = _Scripted([True, True, False, True, True])
    subscriptions.registry.subscribe(state["session"], resources.mailbox_uri(state["mailbox"]))


@when(parsers.parse('servern meddelar att mappresursen för "{mailbox}" har ändrats fem gånger'))
def notify_five(mailbox):
    async def run():
        for _ in range(5):
            await subscriptions.notify_resource_updated(resources.mailbox_uri(mailbox))

    asyncio.run(run())


@then("ska den hängande sessionens prenumerationer vara borttagna")
def slow_forgotten(state):
    assert state["slow"] not in state["left"], f"glömdes inte efter {state['sent']} notiser"
    assert len(state["left"]) == 1


@then("ska det loggas att sessionen glömts")
def logged(state):
    assert "gånger i rad" in state["log"] and "tas bort" in state["log"], state["log"]


@then("ska sessionen som läser fortfarande prenumerera och ha fått varje notis")
def fast_ok(state):
    assert state["fast_received"] == [resources.mailbox_uri(state["mailbox"])] * state["sent"]


@then(parsers.parse('ska sessionen fortfarande prenumerera på mappresursen för "{mailbox}"'))
def still_subscribed(state, mailbox):
    assert subscriptions.registry.subscribers(resources.mailbox_uri(mailbox)) == [
        (state["session"], resources.mailbox_uri(mailbox))
    ]

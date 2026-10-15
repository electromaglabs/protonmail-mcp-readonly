"""BDD: INBOX i resurs-URI:er jämförs utan hänsyn till skiftläge (efterfix-resurser, R4-1)."""
import asyncio

import pytest
from pydantic import AnyUrl
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import subscriptions
from protonmail_mcp.server import notify_new_mail
from tests.efterfix_resurser_support import Collector, client_session

scenarios("efterfix_resurser_inbox.feature")


@pytest.fixture(autouse=True)
def _empty_registry():
    subscriptions.registry.clear()
    yield
    subscriptions.registry.clear()


@pytest.fixture
def state():
    return {"subscribe": [], "received": []}


@given(parsers.parse('att klienten prenumererar på resursen "{uri}"'))
def subscribes(state, uri):
    state["subscribe"].append(uri)


def _run(monkeypatch, state, notify):
    async def run():
        collector = Collector()
        async with client_session(monkeypatch, message_handler=collector) as session:
            for uri in state["subscribe"]:
                await session.subscribe_resource(AnyUrl(uri))
            await notify()
            await session.send_ping()  # notiser före svaret har då nått klienten
        state["received"] = collector.uris

    asyncio.run(run())


@when(parsers.parse('bevakaren meddelar nya mejl i "{mailbox}"'))
def watcher_notifies(monkeypatch, state, mailbox):
    _run(monkeypatch, state, lambda: notify_new_mail(mailbox, [{"uid": "1"}]))


@when(parsers.parse('servern meddelar att resursen "{uri}" har ändrats'))
def server_notifies(monkeypatch, state, uri):
    _run(monkeypatch, state, lambda: subscriptions.notify_resource_updated(uri))


@then(parsers.parse('ska klienten få en notis om att "{uri}" har ändrats'))
def got(state, uri):
    assert state["received"] == [uri]


@then("ska klienten inte få någon notis")
def none(state):
    assert state["received"] == []

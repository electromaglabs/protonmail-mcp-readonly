"""BDD: prenumerationer på resurser, sett via MCP-klienten (mcp-resurser).

Stegen bygger upp en plan (Given) som körs i ett enda asyncio-pass (When),
eftersom klientsessionen inte kan överleva mellan synkrona steg.
"""
import asyncio
from contextlib import AsyncExitStack

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import resources, subscriptions
from tests import sdk_support as sdk
from tests.mcp_resurser_support import client_session

scenarios("mcp_resurser_prenumeration.feature")


@pytest.fixture(autouse=True)
def _empty_registry():
    subscriptions.registry.clear()
    yield
    subscriptions.registry.clear()


@pytest.fixture
def state():
    return {"plan": [], "received": {}, "errors": []}


class _Client:
    """En klientsession som samlar resursnotiser."""

    def __init__(self, name, received):
        self.name = name
        self.received = received.setdefault(name, [])

    async def handler(self, message):
        uri = sdk.resource_updated_uri(message)
        if uri is not None:
            self.received.append(uri)


def _run_plan(monkeypatch, state, notify_uri):
    async def run():
        async with AsyncExitStack() as stack:
            sessions = {}

            async def session_for(name):
                if name not in sessions:
                    client = _Client(name, state["received"])
                    sessions[name] = await stack.enter_async_context(
                        client_session(monkeypatch, message_handler=client.handler)
                    )
                return sessions[name]

            for step, name, uri in state["plan"]:
                if step == "subscribe":
                    await (await session_for(name)).subscribe_resource(uri)
                elif step == "unsubscribe":
                    await (await session_for(name)).unsubscribe_resource(uri)
                elif step == "disconnected":
                    async with client_session(monkeypatch) as gone:
                        await gone.subscribe_resource(uri)
                elif step == "break-first":
                    first, *_ = subscriptions.registry.sessions()

                    async def broken(_uri):
                        raise RuntimeError("trasig session")

                    monkeypatch.setattr(first, "send_resource_updated", broken)

            try:
                await subscriptions.notify_resource_updated(notify_uri)
            except Exception as exc:  # noqa: BLE001 — scenariot kontrollerar det
                state["errors"].append(exc)
            # En rundresa per session: notiser som skickats före svaret har då nått klienten
            for session in sessions.values():
                await session.send_ping()
            state["left"] = subscriptions.registry.subscribers(notify_uri)

    asyncio.run(run())


# --- Given ---------------------------------------------------------------


@given(parsers.parse('att klienten prenumererar på mappresursen för "{mailbox}"'))
def subscribes_mailbox(state, mailbox):
    state["plan"].append(("subscribe", "klient", resources.mailbox_uri(mailbox)))


@given(parsers.parse('att klienten prenumererar på resursen "{uri}"'))
def subscribes_uri(state, uri):
    state["plan"].append(("subscribe", "klient", uri))


@given(parsers.parse('att klienten avslutar prenumerationen på mappresursen för "{mailbox}"'))
def unsubscribes(state, mailbox):
    state["plan"].append(("unsubscribe", "klient", resources.mailbox_uri(mailbox)))


@given(parsers.parse('att en klient som prenumererar på mappresursen för "{mailbox}" har kopplat ner'))
def disconnected(state, mailbox):
    state["plan"].append(("disconnected", "borta", resources.mailbox_uri(mailbox)))


@given(parsers.parse('att två sessioner prenumererar på mappresursen för "{mailbox}"'))
def two_sessions(state, mailbox):
    uri = resources.mailbox_uri(mailbox)
    state["plan"] += [("subscribe", "första", uri), ("subscribe", "andra", uri)]


@given("att notisen till den första sessionen misslyckas")
def first_fails(state):
    state["plan"].append(("break-first", None, None))


# --- When ----------------------------------------------------------------


@when("klienten ansluter")
def connects(monkeypatch, state):
    async def run():
        async with client_session(monkeypatch) as session:
            return sdk.init_info(session)["capabilities"]

    state["capabilities"] = asyncio.run(run())


@when(parsers.parse('servern meddelar att mappresursen för "{mailbox}" har ändrats'))
def notify(monkeypatch, state, mailbox):
    _run_plan(monkeypatch, state, resources.mailbox_uri(mailbox))


@when(parsers.parse('klienten försöker prenumerera på resursen "{uri}"'))
def try_subscribe(monkeypatch, state, uri):
    async def run():
        async with client_session(monkeypatch) as session:
            try:
                await session.subscribe_resource(uri)
            except sdk.MCPError as exc:
                return sdk.error_message(exc)
        return None

    state["error"] = asyncio.run(run())


# --- Then ----------------------------------------------------------------


@then("ska serverns förmågor ha resources.subscribe satt")
def subscribe_capability(state):
    assert state["capabilities"].get("resources") is not None
    assert state["capabilities"]["resources"].get("subscribe") is True


@then(parsers.parse('ska klienten få en notis om att "{uri}" har ändrats'))
def got_notification(state, uri):
    assert state["received"]["klient"] == [uri]


@then("ska klienten inte få någon notis")
def no_notification(state):
    assert state["received"].get("klient", []) == []


@then("ska meddelandet inte misslyckas")
def notify_ok(state):
    assert state["errors"] == []


@then(parsers.parse('ska ingen prenumeration finnas kvar på mappresursen för "{mailbox}"'))
def none_left(state, mailbox):
    assert state["left"] == []
    assert subscriptions.registry.sessions() == []


@then("ska den andra sessionen ändå få notisen")
def second_got_it(state):
    assert state["errors"] == []
    assert state["received"]["andra"] == [resources.mailbox_uri("INBOX")]
    assert state["received"]["första"] == []


@then(parsers.parse('ska prenumerationen misslyckas med texten "{text}"'))
def subscribe_refused(state, text):
    assert state["error"] is not None, "prenumerationen godtogs"
    assert text in state["error"]

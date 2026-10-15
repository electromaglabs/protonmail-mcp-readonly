"""BDD: notiser efter lyckade skrivverktyg (efterfix-resurser, R4-2).

Verktygen anropas via en riktig MCP-klientsession i minnet (klient → MCPServer →
verktyg), med attrapper i stället för Bridge och SMTP.
"""
import asyncio
import time
from unittest.mock import AsyncMock

import anyio
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import imap_bulk, subscriptions
from tests import sdk_support as sdk
from tests.efterfix_resurser_support import Collector, client_session
from tests.mcp_resurser_support import fake_imap

scenarios("efterfix_resurser_verktygsnotiser.feature")


def _split(text):
    return [part.strip() for part in text.split(",") if part.strip()]


@pytest.fixture(autouse=True)
def _empty_registry():
    subscriptions.registry.clear()
    yield
    subscriptions.registry.clear()


@pytest.fixture
def state():
    imap = fake_imap()
    for method in ("set_flags", "move_message", "delete_message", "create_folder",
                   "delete_folder", "rename_folder"):
        getattr(imap, method).return_value = True
    smtp = AsyncMock()
    smtp.send_email.return_value = True
    return {"imap": imap, "smtp": smtp, "subscribe": [], "received": [], "error": None}


@given(parsers.parse('att klienten prenumererar på "{uris}"'))
def subscribes(state, uris):
    state["subscribe"] = _split(uris)


@given(parsers.parse('att markeringen lyckas för UID "{ok}" men misslyckas för UID "{bad}"'))
def partial(monkeypatch, ok, bad):
    async def set_flags(imap, mailbox, uids, flags, add):
        return {"ok": [ok], "failed": [{"uid": bad, "error": "finns inte"}]}

    monkeypatch.setattr(imap_bulk, "set_flags", set_flags)


@given("att Bridge nekar markeringen")
def refused(state):
    state["imap"].set_flags.side_effect = RuntimeError("Bridge nekade STORE")


@given("att notiserna till prenumeranterna hänger")
def hanging(monkeypatch, state):
    state["hang"] = anyio.Event()

    async def stuck(uri):
        await state["hang"].wait()

    monkeypatch.setattr(subscriptions, "notify_resource_updated", stuck)


def _call(monkeypatch, state, tool, arguments):
    async def run():
        collector = Collector()
        async with client_session(
            monkeypatch, imap=state["imap"], smtp=state["smtp"], message_handler=collector
        ) as session:
            for uri in state["subscribe"]:
                await session.subscribe_resource(uri)
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(session.call_tool(tool, arguments), 3)
                state["error"] = result.content[0].text if sdk.wire(result).get("isError") else None
            except sdk.MCPError as exc:
                state["error"] = sdk.error_message(exc)
            state["elapsed"] = time.monotonic() - started
            if "hang" in state:
                state["hang"].set()
            await subscriptions.wait_for_pending_notices()
            await session.send_ping()  # notiser före svaret har då nått klienten
        state["received"] = collector.uris

    asyncio.run(run())


@when(parsers.parse('klienten anropar {tool:w} med uid "{uid}" i mappen "{mailbox}"'))
def call_uid(monkeypatch, state, tool, uid, mailbox):
    _call(monkeypatch, state, tool, {"uid": uid, "mailbox": mailbox})


@when(parsers.parse('klienten anropar {tool:w} med uid-listan "{uids}" i mappen "{mailbox}"'))
def call_uids(monkeypatch, state, tool, uids, mailbox):
    _call(monkeypatch, state, tool, {"uid": _split(uids), "mailbox": mailbox})


@when(parsers.parse('klienten anropar move_email med uid "{uid}" från "{source}" till "{target}"'))
def call_move(monkeypatch, state, uid, source, target):
    _call(monkeypatch, state, "move_email", {"uid": uid, "mailbox": source, "target_mailbox": target})


@when(parsers.parse('klienten anropar create_folder med namnet "{name}"'))
def call_create(monkeypatch, state, name):
    _call(monkeypatch, state, "create_folder", {"name": name})


@when(parsers.parse('klienten byter namn på mappen "{old}" till "{new}"'))
def call_rename(monkeypatch, state, old, new):
    _call(monkeypatch, state, "rename_folder", {"old_name": old, "new_name": new})


@when("klienten skickar ett mejl med send_email")
def call_send(monkeypatch, state):
    _call(monkeypatch, state, "send_email", {"to": "anna@example.com", "subject": "Hej", "body": "Hej!"})


@when(parsers.parse('klienten anropar list_emails i mappen "{mailbox}"'))
def call_list(monkeypatch, state, mailbox):
    _call(monkeypatch, state, "list_emails", {"mailbox": mailbox})


@when("klienten listar resursmallarna")
def list_templates(monkeypatch, state):
    async def run():
        async with client_session(monkeypatch) as session:
            templates = sdk.wire(await session.list_resource_templates())["resourceTemplates"]
            resources = sdk.wire(await session.list_resources())["resources"]
            return {t["name"]: t.get("description") for t in [*templates, *resources]}

    state["descriptions"] = asyncio.run(run())


@then(parsers.parse('ska klienten få notiser om "{uris}"'))
def got(state, uris):
    assert state["error"] is None, state["error"]
    assert sorted(state["received"]) == sorted(_split(uris))


@then("ska klienten inte få någon notis")
def none(state):
    assert state["received"] == []


@then("ska anropet misslyckas")
def failed(state):
    assert state["error"] is not None


@then("ska verktygssvaret komma utan att vänta på notiserna")
def not_delayed(state):
    assert state["error"] is None, state["error"]
    assert state["elapsed"] < 1.0, f"svaret tog {state['elapsed']:.2f} s"


@then(parsers.parse('ska beskrivningen av "{name}" nämna "{first}" och "{second}"'))
def describes(state, name, first, second):
    description = state["descriptions"][name]
    assert first in description and second in description, description

"""Kroken på mcp:s riktiga ServerSession (efterfix-resurser, R4-4).

subscriptions.SubscriptionRegistry glömmer en session via BaseSession._exit_stack,
som är privat API i mcp. Testerna här använder en riktig ServerSession i minnet,
så att de faller om mcp byter namn på attributet eller slutar stänga det.
"""
import asyncio
from contextlib import AsyncExitStack

import pytest
from pydantic import AnyUrl

from protonmail_mcp import subscriptions
from tests.efterfix_resurser_support import client_session


@pytest.fixture(autouse=True)
def _empty_registry():
    subscriptions.registry.clear()
    yield
    subscriptions.registry.clear()


def _subscribe_then_disconnect(monkeypatch):
    seen = {}

    async def run():
        async with client_session(monkeypatch) as session:
            await session.subscribe_resource(AnyUrl("mailbox://INBOX"))
            (server_session,) = subscriptions.registry.sessions()
            seen["session"] = server_session
            seen["hooked"] = id(server_session) in subscriptions.registry._hooked
        seen["after"] = subscriptions.registry.sessions()

    asyncio.run(run())
    return seen


def test_real_server_session_has_an_exit_stack(monkeypatch):
    seen = _subscribe_then_disconnect(monkeypatch)
    from mcp.server.session import ServerSession

    assert isinstance(seen["session"], ServerSession)
    assert isinstance(getattr(seen["session"], "_exit_stack", None), AsyncExitStack)


def test_hook_is_attached_to_a_real_session(monkeypatch):
    assert _subscribe_then_disconnect(monkeypatch)["hooked"] is True


def test_real_session_is_forgotten_on_disconnect_without_any_notification(monkeypatch):
    sent = []

    async def no_send(session, uri):  # en notis skulle också städa — den får inte behövas
        sent.append(uri)

    monkeypatch.setattr(subscriptions, "_send", no_send)
    assert _subscribe_then_disconnect(monkeypatch)["after"] == []
    assert sent == []


def test_fails_when_the_hook_does_not_attach(monkeypatch):
    """Kontroll av testet: utan kroken blir sessionen kvar (så testet ovan skyddar något)."""
    monkeypatch.setattr(subscriptions.SubscriptionRegistry, "_forget_on_exit", lambda self, s: None)
    assert len(_subscribe_then_disconnect(monkeypatch)["after"]) == 1

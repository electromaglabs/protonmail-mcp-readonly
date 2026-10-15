"""Kroken på SDK:ns riktiga anslutning (efterfix-resurser, R4-4).

subscriptions.SubscriptionRegistry glömmer en session när anslutningen stängs,
via anslutningens exit-stack (Connection.exit_stack), som den når genom
ServerSession._connection, privat API i mcp. Testerna här använder en riktig
ServerSession i minnet, så att de faller om mcp byter namn på attributen eller
slutar stänga exit-stacken.
"""
import asyncio
from contextlib import AsyncExitStack

import pytest

from protonmail_mcp import subscriptions
from tests.efterfix_resurser_support import client_session


@pytest.fixture(autouse=True)
def _empty_registry():
    subscriptions.registry.clear()
    yield
    subscriptions.registry.clear()


def _subscribe_then_disconnect(monkeypatch, subscriptions_count=1):
    seen = {}

    async def run():
        async with client_session(monkeypatch) as session:
            for _ in range(subscriptions_count):
                await session.subscribe_resource("mailbox://INBOX")
            seen["sessions"] = subscriptions.registry.sessions()
            (server_session,) = seen["sessions"]
            seen["session"] = server_session
            seen["hooked"] = id(server_session) in subscriptions.registry._hooked
        seen["after"] = subscriptions.registry.sessions()

    asyncio.run(run())
    return seen


def test_real_session_has_a_connection_with_an_exit_stack(monkeypatch):
    seen = _subscribe_then_disconnect(monkeypatch)
    from mcp.server.session import ServerSession

    assert isinstance(seen["session"], ServerSession)
    connection = getattr(seen["session"], "_connection", None)
    assert isinstance(getattr(connection, "exit_stack", None), AsyncExitStack)


def test_requests_on_one_connection_are_one_session(monkeypatch):
    """SDK:n ger varje meddelande ett nytt sessionsobjekt; registret ska ändå se en session."""
    assert len(_subscribe_then_disconnect(monkeypatch, subscriptions_count=3)["sessions"]) == 1


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

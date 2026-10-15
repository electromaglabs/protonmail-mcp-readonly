"""Enhetstester: prenumerationsregistret och notiserna (mcp-resurser)."""
import asyncio
from contextlib import AsyncExitStack

import anyio
import pytest

from protonmail_mcp import resources, subscriptions
from protonmail_mcp.server import mcp, register_tools
from tests import sdk_support as sdk


class FakeSession:
    def __init__(self, error=None, delay=0.0):
        self.sent = []
        self.error = error
        self.delay = delay

    async def send_resource_updated(self, uri):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        self.sent.append(str(uri))


@pytest.fixture
def registry():
    return subscriptions.SubscriptionRegistry()


@pytest.fixture(autouse=True)
def _empty_global_registry():
    subscriptions.registry.clear()
    yield
    subscriptions.registry.clear()


class TestRegistry:
    def test_subscribe_and_list(self, registry):
        session = FakeSession()
        registry.subscribe(session, "mailbox://INBOX")
        assert registry.subscribers("mailbox://INBOX") == [(session, "mailbox://INBOX")]

    def test_different_spellings_are_the_same_resource(self, registry):
        session = FakeSession()
        registry.subscribe(session, "mailbox://Folders/A/B")
        assert registry.subscribers(resources.mailbox_uri("Folders/A/B")) == [
            (session, "mailbox://Folders/A/B")
        ]
        registry.unsubscribe(session, "mailbox://Folders%2FA%2FB")
        assert registry.subscribers("mailbox://Folders/A/B") == []

    def test_subscribing_twice_gives_one_entry(self, registry):
        session = FakeSession()
        registry.subscribe(session, "mailbox://INBOX")
        registry.subscribe(session, "mailbox://INBOX")
        assert len(registry.subscribers("mailbox://INBOX")) == 1

    def test_unsubscribe_unknown_is_harmless(self, registry):
        registry.unsubscribe(FakeSession(), "mailbox://INBOX")

    def test_unknown_resource_is_refused(self, registry):
        with pytest.raises(ValueError, match="Okänd resurs"):
            registry.subscribe(FakeSession(), "file:///etc/passwd")

    def test_forget_removes_all_subscriptions_of_a_session(self, registry):
        gone, stays = FakeSession(), FakeSession()
        for uri in ("mailbox://INBOX", "email://INBOX/1"):
            registry.subscribe(gone, uri)
        registry.subscribe(stays, "mailbox://INBOX")
        registry.forget(gone)
        assert registry.sessions() == [stays]
        assert registry.subscribers("email://INBOX/1") == []

    def test_session_is_forgotten_when_it_exits(self, registry):
        async def run():
            session = FakeSession()
            # Utan _connection räknas sessionen som sin egen anslutning
            session.exit_stack = AsyncExitStack()
            registry.subscribe(session, "mailbox://INBOX")
            assert registry.sessions() == [session]
            await session.exit_stack.aclose()

        asyncio.run(run())
        assert registry.sessions() == []


class TestNotify:
    def test_sends_to_all_subscribers_of_the_uri(self):
        a, b, other = FakeSession(), FakeSession(), FakeSession()
        subscriptions.registry.subscribe(a, "mailbox://INBOX")
        subscriptions.registry.subscribe(b, "mailbox://INBOX")
        subscriptions.registry.subscribe(other, "mailbox://Archive")
        asyncio.run(subscriptions.notify_resource_updated("mailbox://INBOX"))
        assert a.sent == b.sent == ["mailbox://INBOX"]
        assert other.sent == []

    def test_no_subscribers_is_fine(self):
        asyncio.run(subscriptions.notify_resource_updated("mailbox://INBOX"))

    def test_invalid_uri_does_not_raise(self):
        asyncio.run(subscriptions.notify_resource_updated("inte en uri"))

    @pytest.mark.parametrize("error", [anyio.BrokenResourceError(), anyio.ClosedResourceError()])
    def test_closed_session_is_removed(self, error):
        closed, open_ = FakeSession(error=error), FakeSession()
        subscriptions.registry.subscribe(closed, "mailbox://INBOX")
        subscriptions.registry.subscribe(open_, "mailbox://INBOX")
        asyncio.run(subscriptions.notify_resource_updated("mailbox://INBOX"))
        assert subscriptions.registry.sessions() == [open_]
        assert open_.sent == ["mailbox://INBOX"]

    def test_other_error_keeps_the_session_and_reaches_the_rest(self, caplog):
        failing, ok = FakeSession(error=RuntimeError("trasig")), FakeSession()
        subscriptions.registry.subscribe(failing, "mailbox://INBOX")
        subscriptions.registry.subscribe(ok, "mailbox://INBOX")
        asyncio.run(subscriptions.notify_resource_updated("mailbox://INBOX"))
        assert ok.sent == ["mailbox://INBOX"]
        assert failing in subscriptions.registry.sessions()
        assert "trasig" in caplog.text

    def test_slow_session_does_not_block_the_others(self, monkeypatch):
        monkeypatch.setattr(subscriptions, "SEND_TIMEOUT_SECONDS", 0.05)
        slow, ok = FakeSession(delay=5), FakeSession()
        subscriptions.registry.subscribe(slow, "mailbox://INBOX")
        subscriptions.registry.subscribe(ok, "mailbox://INBOX")

        async def run():
            with anyio.fail_after(2):
                await subscriptions.notify_resource_updated("mailbox://INBOX")

        asyncio.run(run())
        assert ok.sent == ["mailbox://INBOX"]

    def test_notification_uses_the_subscribed_spelling(self):
        session = FakeSession()
        subscriptions.registry.subscribe(session, "mailbox://Folders/A/B")
        asyncio.run(subscriptions.notify_resource_updated(resources.mailbox_uri("Folders/A/B")))
        assert session.sent == ["mailbox://Folders/A/B"]


class TestRegistration:
    def test_capabilities_announce_subscribe(self):
        register_tools()
        assert sdk.capabilities(mcp)["resources"]["subscribe"] is True

    def test_register_is_idempotent(self):
        register_tools()
        subscriptions.register(mcp)
        subscriptions.register(mcp)
        caps = sdk.capabilities(mcp, resources_changed=True)
        assert caps["resources"]["subscribe"] is True
        assert caps["resources"]["listChanged"] is True

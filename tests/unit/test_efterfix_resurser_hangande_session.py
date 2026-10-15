"""Tidsgränser i rad: en hängande session glöms efter MAX_CONSECUTIVE_TIMEOUTS (efterfix-resurser, R4-3)."""
import asyncio
import logging

import pytest

from protonmail_mcp import subscriptions

URI = "mailbox://INBOX"


class Session:
    def __init__(self, slow):
        self.slow = list(slow)  # per anrop: True = för långsam
        self.sent = []

    async def send_resource_updated(self, uri):
        if self.slow.pop(0) if self.slow else False:
            await asyncio.sleep(1)
        self.sent.append(str(uri))


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    subscriptions.registry.clear()
    monkeypatch.setattr(subscriptions, "SEND_TIMEOUT_SECONDS", 0.05)
    yield
    subscriptions.registry.clear()


def _notify(times):
    async def run():
        for _ in range(times):
            await subscriptions.notify_resource_updated(URI)

    asyncio.run(run())


def test_limit_is_three():
    assert subscriptions.MAX_CONSECUTIVE_TIMEOUTS == 3


def test_forgotten_after_n_timeouts_in_a_row(caplog):
    hanging, ok = Session([True] * 10), Session([])
    subscriptions.registry.subscribe(hanging, URI)
    subscriptions.registry.subscribe(hanging, "email://INBOX/1")
    subscriptions.registry.subscribe(ok, URI)
    with caplog.at_level(logging.WARNING, logger="protonmail_mcp.subscriptions"):
        _notify(subscriptions.MAX_CONSECUTIVE_TIMEOUTS - 1)
        assert hanging in subscriptions.registry.sessions()
        _notify(1)
    assert subscriptions.registry.sessions() == [ok]
    assert subscriptions.registry.subscribers("email://INBOX/1") == []
    assert ok.sent == [URI] * subscriptions.MAX_CONSECUTIVE_TIMEOUTS
    assert "tas bort" in caplog.text


def test_success_resets_the_count():
    flaky = Session([True, True, False, True, True, False, True, True])
    subscriptions.registry.subscribe(flaky, URI)
    _notify(8)
    assert subscriptions.registry.sessions() == [flaky]


def test_forget_clears_the_count():
    s = Session([True, True, False])
    subscriptions.registry.subscribe(s, URI)
    _notify(2)
    subscriptions.registry.forget(s)
    assert subscriptions.registry._timeouts == {}


def test_clear_clears_the_counts():
    s = Session([True])
    subscriptions.registry.subscribe(s, URI)
    _notify(1)
    subscriptions.registry.clear()
    assert subscriptions.registry._timeouts == {}


def test_other_errors_do_not_count_as_timeouts():
    class Broken:
        async def send_resource_updated(self, uri):
            raise RuntimeError("trasig")

    b = Broken()
    subscriptions.registry.subscribe(b, URI)
    _notify(5)
    assert subscriptions.registry.sessions() == [b]

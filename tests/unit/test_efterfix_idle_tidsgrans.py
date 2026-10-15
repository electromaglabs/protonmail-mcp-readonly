"""Enhetstester: wait_for_new_email håller timeout_seconds (plus marginal) (G4I-5)."""
import asyncio
import time
from types import SimpleNamespace

import pytest

from protonmail_mcp.tools import new_mail


def _ctx():
    app = SimpleNamespace(imap=None, watcher=None)
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app))


async def test_hanging_poll_is_cancelled_after_timeout_plus_margin(monkeypatch):
    monkeypatch.setattr(new_mail, "DEADLINE_MARGIN", 0.2)
    cancelled = asyncio.Event()

    async def hanging(app, mailbox, since_uid):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(new_mail, "_collect", hanging)
    begin = time.monotonic()
    with pytest.raises(asyncio.TimeoutError, match="svarade inte inom 1 s"):
        await new_mail.wait_for_new_email(_ctx(), mailbox="INBOX", timeout_seconds=1)
    assert time.monotonic() - begin < 2
    assert cancelled.is_set(), "den hängande frågan ska avbrytas (så att låset släpps)"


async def test_errors_from_the_poll_are_passed_through(monkeypatch):
    async def failing(app, mailbox, since_uid):
        raise asyncio.TimeoutError("ProtonMail Bridge svarade inte på SELECT inom 2 s")

    monkeypatch.setattr(new_mail, "_collect", failing)
    with pytest.raises(asyncio.TimeoutError, match="på SELECT"):
        await new_mail.wait_for_new_email(_ctx(), mailbox="INBOX", timeout_seconds=5)


async def test_caller_cancellation_also_cancels_the_poll(monkeypatch):
    cancelled = asyncio.Event()

    async def hanging(app, mailbox, since_uid):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(new_mail, "_collect", hanging)
    task = asyncio.create_task(new_mail.wait_for_new_email(_ctx(), mailbox="INBOX", timeout_seconds=60))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()

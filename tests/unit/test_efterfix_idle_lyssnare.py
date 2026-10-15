"""Enhetstester: lyssnarna körs som egna uppgifter som stop() städar (R4-3)."""
import asyncio
import logging

from protonmail_mcp import imap_idle
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_idle import MailWatcher


def _watcher():
    return MailWatcher(Settings(username="u", password="p", imap_port=1, _env_file=None))


def _msg(uid):
    return {"uid": str(uid), "mailbox": "INBOX", "subject": f"m{uid}"}


async def test_schedule_does_not_wait_for_the_listener():
    w = _watcher()
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(mailbox, messages):
        started.set()
        await release.wait()

    w.add_listener(slow)
    w._schedule_notify("INBOX", [_msg(4)])  # returnerar direkt
    assert len(w._notify_tasks) == 1
    await asyncio.wait_for(started.wait(), 1)
    release.set()
    await asyncio.sleep(0.01)
    assert w._notify_tasks == set(), "klara uppgifter släpps"


async def test_failing_listener_in_a_task_is_logged(caplog):
    w = _watcher()

    async def broken(mailbox, messages):
        raise RuntimeError("trasig lyssnare")

    w.add_listener(broken)
    w._schedule_notify("INBOX", [_msg(4)])
    await asyncio.sleep(0.01)
    assert "trasig lyssnare" in caplog.text
    assert w._notify_tasks == set()


async def test_no_listeners_no_task():
    w = _watcher()
    w._schedule_notify("INBOX", [_msg(4)])
    assert w._notify_tasks == set()


async def test_pending_notifications_are_bounded(monkeypatch, caplog):
    monkeypatch.setattr(imap_idle, "MAX_PENDING_NOTIFICATIONS", 2)
    w = _watcher()

    async def hangs(mailbox, messages):
        await asyncio.Event().wait()

    w.add_listener(hangs)
    with caplog.at_level(logging.WARNING):
        for uid in (4, 5, 6):
            w._schedule_notify("INBOX", [_msg(uid)])
    assert len(w._notify_tasks) == 2
    assert "hoppas över" in caplog.text
    await w.stop()
    assert w._notify_tasks == set()


async def test_stop_cancels_running_listeners():
    w = _watcher()
    cancelled = asyncio.Event()

    async def hangs(mailbox, messages):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    w.add_listener(hangs)
    w._schedule_notify("INBOX", [_msg(4)])
    await asyncio.sleep(0.01)
    await asyncio.wait_for(w.stop(), 3)
    assert cancelled.is_set()
    assert w._notify_tasks == set()

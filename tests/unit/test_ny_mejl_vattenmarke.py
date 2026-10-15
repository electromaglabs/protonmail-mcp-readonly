"""Enhetstester: vattenmärket kan inte förgiftas (ny-mejl, säkerhetsgranskning)."""
import asyncio
from types import SimpleNamespace

import pytest

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.imap_idle import MailWatcher, poll_new_messages
from protonmail_mcp.tools import new_mail
from tests.ny_mejl_fakeidle import FakeIdleBridge


@pytest.fixture
async def bridge():
    fake = FakeIdleBridge()
    fake.add_box("INBOX", [1, 2, 3])
    await fake.start()
    yield fake
    await fake.stop()


def _settings(port, **kw):
    return Settings(username="u", password="p", imap_port=port, imap_timeout=2, _env_file=None, **kw)


async def _app(port, enabled):
    watcher = MailWatcher(_settings(port, watch_enabled=enabled))
    watcher.start()
    return SimpleNamespace(imap=IMAPClient(_settings(port)), smtp=None, watcher=watcher)


async def _close(app):
    await app.watcher.stop()
    await app.imap.disconnect()


def _ctx(app):
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app))


async def test_poll_never_reports_a_mark_past_the_newest_message(bridge):
    imap = IMAPClient(_settings(bridge.port))
    try:
        result = await poll_new_messages(imap, "INBOX", 999999999, 1, 50)
    finally:
        await imap.disconnect()
    assert result["messages"] == []
    assert result["last_uid"] == 3
    assert result["clamped"] is True


@pytest.mark.parametrize("enabled", [True, False])
async def test_since_uid_never_writes_the_mark(bridge, enabled):
    app = await _app(bridge.port, enabled)
    try:
        for _ in range(200):
            if not enabled or app.watcher.is_watching("INBOX"):
                break
            await asyncio.sleep(0.01)
        await new_mail.check_new_emails(_ctx(app), mailbox="INBOX")
        before = dict(app.watcher.marks)
        await new_mail.check_new_emails(_ctx(app), mailbox="INBOX", since_uid="999999999")
        await new_mail.check_new_emails(_ctx(app), mailbox="INBOX", since_uid="0")
        assert app.watcher.marks == before
    finally:
        await _close(app)


@pytest.mark.parametrize("enabled", [True, False])
async def test_poisoned_mark_is_pulled_back_with_a_note(bridge, enabled):
    """Ett märke förbi det senaste mejlet (t.ex. från en äldre version) dras tillbaka."""
    app = await _app(bridge.port, enabled)
    try:
        for _ in range(200):
            if not enabled or app.watcher.is_watching("INBOX"):
                break
            await asyncio.sleep(0.01)
        app.watcher.marks["INBOX"] = (1, 999999999)
        result = await new_mail.check_new_emails(_ctx(app), mailbox="INBOX")
        assert app.watcher.marks["INBOX"] == (1, 3)
        assert "list_emails" in result["note"]
        bridge.deliver("INBOX", subject="Ny")
        await asyncio.sleep(0.2)
        result = await new_mail.check_new_emails(_ctx(app), mailbox="INBOX")
        assert [m["uid"] for m in result["messages"]] == ["4"]
    finally:
        await _close(app)


def test_watcher_queue_refuses_marks_ahead_of_what_it_has_seen():
    w = MailWatcher(_settings(1))
    st = w._states["INBOX"]
    st.uidvalidity, st.floor, st.watermark, st.baseline, st.connected = 1, 3, 3, 3, True
    assert w.messages_since("INBOX", 3, 1) == []
    assert w.messages_since("INBOX", 4, 1) is None

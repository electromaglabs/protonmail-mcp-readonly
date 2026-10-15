"""Enhetstester: mejl som kommer under bevakningens sökning, hämtning eller förnyelse (G4I-1)."""
import asyncio
from unittest.mock import MagicMock

from protonmail_mcp import imap_idle
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_idle import MailWatcher, _WatchProtocol
from tests.ny_mejl_fakeidle import FakeIdleBridge


def _settings(port):
    return Settings(username="u", password="p", imap_port=port, imap_timeout=2, _env_file=None)


async def _eventually(predicate, timeout=3.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        assert loop.time() < deadline, "villkoret uppfylldes inte"
        await asyncio.sleep(0.01)


def _protocol():
    return _WatchProtocol(asyncio.get_running_loop())


async def test_exists_outside_a_sync_command_is_noticed():
    """EXISTS i svaret på UID SEARCH/FETCH kastas av aioimaplib; bevakningen ska märka det."""
    protocol = _protocol()
    assert protocol.saw_push is False
    protocol._untagged_response(b"* 5 EXISTS")
    assert protocol.saw_push is True


async def test_recent_outside_a_sync_command_is_noticed():
    protocol = _protocol()
    protocol._untagged_response(b"* 1 RECENT")
    assert protocol.saw_push is True


async def test_exists_in_select_or_idle_is_not_a_missed_push():
    """Under SELECT och IDLE (synkrona kommandon) hör EXISTS till kommandot."""
    protocol = _protocol()
    protocol.pending_sync_command = MagicMock()
    protocol._untagged_response(b"* 5 EXISTS")
    assert protocol.saw_push is False
    protocol.pending_sync_command.append_to_resp.assert_called_once_with(b"5 EXISTS")


async def test_other_untagged_lines_are_not_pushes():
    protocol = _protocol()
    protocol._untagged_response(b"* 3 EXPUNGE")
    protocol._untagged_response(b"* SEARCH 1 2")
    assert protocol.saw_push is False


async def _watch(fake, **kw):
    w = MailWatcher(_settings(fake.port), **kw)
    w.start()
    await _eventually(lambda: w.is_watching("INBOX"))
    return w


def _queue(w):
    return sorted(int(m["uid"]) for m in w.recent_events("INBOX"))


async def test_mail_during_fetch_is_picked_up_without_waiting_for_renewal():
    fake = FakeIdleBridge()
    fake.add_box("INBOX", [1, 2, 3])
    await fake.start()
    w = await _watch(fake, renew_seconds=60)
    try:
        fake.during("UID FETCH", lambda: fake.deliver("INBOX", subject="under hämtningen"))
        fake.deliver("INBOX", subject="först")
        await _eventually(lambda: _queue(w) == [4, 5])
    finally:
        await w.stop()
        await fake.stop()


async def test_every_idle_round_ends_with_a_search_even_without_push():
    """Förnyelsen söker också, så en EXISTS som kom mellan DONE och OK inte tappas."""
    fake = FakeIdleBridge()
    fake.add_box("INBOX", [1, 2, 3])
    await fake.start()
    w = await _watch(fake, renew_seconds=0.1)
    try:
        await _eventually(lambda: fake.idle_count() >= 4)
        searches = [line for _, line in fake.commands if "UID SEARCH" in line.upper()]
        assert len(searches) >= 3
    finally:
        await w.stop()
        await fake.stop()


class _ChattyBridge(FakeIdleBridge):
    """Skickar EXISTS i svaret på varje kommando, för evigt."""

    def _flush(self, conn):
        return "* 3 EXISTS\r\n" if conn.selected and conn.idle_tag is None else ""


async def test_catch_up_is_bounded_when_bridge_keeps_sending_exists():
    fake = _ChattyBridge()
    fake.add_box("INBOX", [1, 2, 3])
    await fake.start()
    w = await _watch(fake, renew_seconds=60)
    try:
        fake.deliver("INBOX")
        await _eventually(lambda: _queue(w) == [4])
        await _eventually(lambda: fake.idle_count() >= 2)
        searches = [line for _, line in fake.commands if "UID SEARCH" in line.upper()]
        assert len(searches) <= imap_idle.CATCH_UP_ROUNDS
        assert w.is_watching("INBOX")
    finally:
        await w.stop()
        await fake.stop()

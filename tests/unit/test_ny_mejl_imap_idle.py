"""Enhetstester: MailWatcher och hjälparna i imap_idle (ny-mejl)."""
import asyncio
from types import SimpleNamespace

import pytest

from protonmail_mcp import imap_idle
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.imap_idle import MailWatcher
from tests.ny_mejl_fakeidle import FakeIdleBridge


def _settings(port=1, **kw):
    return Settings(username="u", password="p", imap_port=port, imap_timeout=2, _env_file=None, **kw)


def _msg(uid, mailbox="INBOX"):
    return {"uid": str(uid), "mailbox": mailbox, "subject": f"m{uid}", "from": "a@b", "to": "",
            "date": "", "message_id": "", "flags": []}


def test_renewal_is_well_before_29_minutes():
    assert imap_idle.DEFAULT_RENEW_SECONDS < 29 * 60
    assert imap_idle.DEFAULT_RENEW_SECONDS >= 60


def test_backoff_cap_is_five_minutes():
    assert imap_idle.BACKOFF_MAX == 300.0


def test_renewal_shorter_than_29_minutes_is_required():
    with pytest.raises(ValueError, match="29 minuter"):
        MailWatcher(_settings(), renew_seconds=29 * 60)


@pytest.mark.parametrize("line, expected", [
    (b"5 EXISTS", True),
    (b"* 5 EXISTS", True),
    (b"1 RECENT", True),
    (b"3 EXPUNGE", False),
    (b"2 FETCH (FLAGS (\\Seen))", False),
    (b"OK still here", False),
])
def test_push_detection(line, expected):
    assert imap_idle._is_new_mail_push([line]) is expected


def test_select_info_parsed():
    resp = SimpleNamespace(result="OK", lines=[
        b"FLAGS (\\Seen)", b"3 EXISTS", b"0 RECENT",
        b"OK [UIDVALIDITY 1700000000] UIDs valid", b"OK [UIDNEXT 42] Predicted", b"[READ-WRITE] SELECT completed",
    ])
    info = imap_idle._parse_select(resp)
    assert info == imap_idle.MailboxInfo(uidvalidity=1700000000, uidnext=42, exists=3)


def test_mailbox_key_inbox_case_insensitive():
    assert imap_idle.mailbox_key("inbox") == "INBOX"
    assert imap_idle.mailbox_key("Folders/Inbox") == "Folders/Inbox"


def _watching_state(watcher, mailbox="INBOX", floor=10, uidvalidity=1):
    st = watcher._states[imap_idle.mailbox_key(mailbox)]
    st.uidvalidity, st.floor, st.watermark, st.baseline = uidvalidity, floor, floor, floor
    st.connected = True
    return st


def test_messages_since_uses_queue():
    w = MailWatcher(_settings())
    st = _watching_state(w)
    w._record(st, [_msg(12), _msg(11)])
    assert [m["uid"] for m in w.messages_since("INBOX", 10, 1)] == ["12", "11"]
    assert [m["uid"] for m in w.messages_since("inbox", 11, 1)] == ["12"]
    assert w.messages_since("INBOX", 12, 1) == []


def test_messages_since_cannot_answer_below_floor_or_other_uidvalidity():
    w = MailWatcher(_settings())
    _watching_state(w)
    assert w.messages_since("INBOX", 9, 1) is None  # äldre än bevakningen
    assert w.messages_since("INBOX", 10, 2) is None  # annat UIDVALIDITY
    assert w.messages_since("Folders/X", 10, 1) is None  # bevakas inte


def test_queue_is_bounded_and_raises_floor():
    w = MailWatcher(_settings(), queue_size=3)
    st = _watching_state(w)
    w._record(st, [_msg(u) for u in (15, 14, 13, 12, 11)])
    assert [m["uid"] for m in w.recent_events("INBOX")] == ["15", "14", "13"]
    assert w.messages_since("INBOX", 10, 1) is None  # 11 och 12 har fallit ur kön
    assert [m["uid"] for m in w.messages_since("INBOX", 12, 1)] == ["15", "14", "13"]


def test_record_sets_last_event():
    w = MailWatcher(_settings())
    st = _watching_state(w)
    assert w.status("INBOX")["last_event"] is None
    w._record(st, [_msg(11)])
    assert w.status("INBOX")["last_event"].endswith("+00:00")


async def test_wait_for_messages_wakes_on_new_batch():
    w = MailWatcher(_settings())
    st = _watching_state(w)

    async def later():
        await asyncio.sleep(0.05)
        w._record(st, [_msg(11)])

    task = asyncio.create_task(later())
    msgs = await w.wait_for_messages("INBOX", 10, 1, timeout=2)
    await task
    assert [m["uid"] for m in msgs] == ["11"]


async def test_wait_for_messages_times_out_with_empty_list():
    w = MailWatcher(_settings())
    _watching_state(w)
    assert await w.wait_for_messages("INBOX", 10, 1, timeout=0.05) == []


async def test_listeners_called_and_removable():
    w = MailWatcher(_settings())
    calls = []

    async def listener(mailbox, messages):
        calls.append((mailbox, [m["uid"] for m in messages]))

    w.add_listener(listener)
    await w._notify("INBOX", [_msg(11)])
    w.remove_listener(listener)
    await w._notify("INBOX", [_msg(12)])
    assert calls == [("INBOX", ["11"])]


async def test_failing_listener_is_logged_not_raised(caplog):
    w = MailWatcher(_settings())

    async def broken(mailbox, messages):
        raise RuntimeError("trasig")

    w.add_listener(broken)
    await w._notify("INBOX", [_msg(11)])
    assert "trasig" in caplog.text


async def test_disabled_watcher_starts_no_tasks():
    w = MailWatcher(_settings(watch_enabled=False))
    w.start()
    assert w._tasks == {}
    assert w.status("INBOX") == {"watching": False, "last_event": None, "last_error": None}
    await w.stop()


async def test_stop_is_idempotent_and_wakes_waiters():
    w = MailWatcher(_settings())
    _watching_state(w)
    waiter = asyncio.create_task(w.wait_for_messages("INBOX", 10, 1, timeout=5))
    await asyncio.sleep(0.01)
    await w.stop()
    await w.stop()
    assert await asyncio.wait_for(waiter, 1) == []


async def test_server_without_idle_is_reported():
    fake = FakeIdleBridge(idle=False)
    fake.add_box("INBOX", [1])
    port = await fake.start()

    async def no_sleep(_delay):
        await asyncio.sleep(0.01)

    w = MailWatcher(_settings(port), sleep=no_sleep)
    w.start()
    try:
        for _ in range(200):
            if w.status("INBOX")["last_error"]:
                break
            await asyncio.sleep(0.01)
        assert "IDLE" in w.status("INBOX")["last_error"]
        assert not w.is_watching("INBOX")
    finally:
        await w.stop()
        await fake.stop()


async def test_new_messages_fetched_with_peek_and_filtered_by_watermark():
    """"n:*" ger alltid det sista mejlet; bara UID > vattenmärket räknas."""
    fake = FakeIdleBridge()
    fake.add_box("INBOX", [1, 2, 3])
    port = await fake.start()
    imap = IMAPClient(_settings(port))
    try:
        await imap.connect()
        info = await imap_idle.select_info(imap, "INBOX")
        assert info.uidnext == 4 and info.uidvalidity == 1
        assert await imap_idle.new_uids(imap, 3) == []
        fake.deliver("INBOX", subject="Ny")
        assert await imap_idle.new_uids(imap, 3) == [4]
        msgs = await imap_idle.fetch_metadata(imap, "INBOX", [4])
        assert [(m["uid"], m["subject"], m["mailbox"]) for m in msgs] == [("4", "Ny", "INBOX")]
        assert all("BODY.PEEK[" in line for line in fake.fetch_lines())
    finally:
        await imap.disconnect()
        await fake.stop()


async def test_stop_finishes_even_if_a_cancellation_is_swallowed():
    """Python 3.10:s wait_for kan svälja en avbrytning (fixat i 3.12); stop() får ändå inte hänga."""
    w = MailWatcher(_settings())
    swallowed = asyncio.Event()

    async def stubborn():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            swallowed.set()  # som wait_for i 3.10: avbrytningen försvinner
        await asyncio.sleep(3600)  # väntar vidare som en ny IDLE-omgång

    w._tasks["INBOX"] = asyncio.create_task(stubborn(), name="protonmail-watch:INBOX")
    await asyncio.sleep(0)
    await asyncio.wait_for(w.stop(), 3)
    assert swallowed.is_set()
    assert w._tasks == {}


async def test_idle_not_started_when_stopping():
    w = MailWatcher(_settings())
    w._stopping = True
    client = SimpleNamespace()  # inga attribut: ett IDLE-försök skulle ge AttributeError
    assert await w._idle(SimpleNamespace(timeout=1), client) is False

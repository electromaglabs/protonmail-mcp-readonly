"""Enhetstester: mejl som kom medan bevakningen var nere och UIDVALIDITY byttes (G4I-4)."""
from datetime import datetime, timedelta, timezone

import pytest

from protonmail_mcp import imap_idle
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from tests.ny_mejl_fakeidle import FakeIdleBridge


@pytest.mark.parametrize("text, expected", [
    ("15-Oct-2026 09:00:00 +0200", datetime(2026, 10, 15, 7, 0, tzinfo=timezone.utc)),
    (" 5-Oct-2026 09:00:00 +0000", datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)),
    ("5-oct-2026 09:00:00 -0130", datetime(2026, 10, 5, 10, 30, tzinfo=timezone.utc)),
])
def test_internaldate_parsed_to_utc(text, expected):
    assert imap_idle._parse_internaldate(text) == expected


def test_garbage_internaldate_is_none():
    assert imap_idle._parse_internaldate("igår") is None


def test_since_criterion_is_locale_independent():
    assert imap_idle._imap_date(datetime(2026, 3, 4, tzinfo=timezone.utc)) == "04-Mar-2026"


async def _imap(fake):
    await fake.start()
    imap = IMAPClient(Settings(username="u", password="p", imap_port=fake.port, imap_timeout=2,
                               _env_file=None))
    await imap.connect()
    await imap._select("INBOX")
    return imap


async def test_recover_finds_mail_after_cutoff_and_skips_known_message_ids():
    fake = FakeIdleBridge()
    fake.add_box("INBOX", [1, 2])  # en timme gamla
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    fake.deliver("INBOX", subject="Redan visat")
    fake.deliver("INBOX", subject="Nytt")
    imap = await _imap(fake)
    try:
        msgs = await imap_idle.recover_messages(imap, "INBOX", cutoff, {"<3@example.com>"})
        assert [m["subject"] for m in msgs] == ["Nytt"]
        assert all("BODY.PEEK[" in line or "INTERNALDATE" in line for line in fake.fetch_lines())
    finally:
        await imap.disconnect()
        await fake.stop()


async def test_recover_in_mailbox_without_recent_mail_is_empty():
    fake = FakeIdleBridge()
    fake.add_box("INBOX", [1, 2])
    imap = await _imap(fake)
    try:
        assert await imap_idle.recover_messages(imap, "INBOX", datetime.now(timezone.utc), set()) == []
    finally:
        await imap.disconnect()
        await fake.stop()

"""Enhetstester: UID-sökningen i en tom mapp (Bridge svarar NO no such message) (G4I-3)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from protonmail_mcp import imap_idle
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from tests.ny_mejl_fakeidle import FakeIdleBridge


def _imap(resp):
    return SimpleNamespace(_client=SimpleNamespace(uid_search=AsyncMock(return_value=resp)))


async def test_no_such_message_means_no_new_mail():
    resp = SimpleNamespace(result="NO", lines=[b"no such message"])
    assert await imap_idle.new_uids(_imap(resp), 0) == []


async def test_other_refusals_still_raise():
    resp = SimpleNamespace(result="NO", lines=[b"mailbox is busy"])
    with pytest.raises(ValueError, match="mailbox is busy"):
        await imap_idle.new_uids(_imap(resp), 0)


async def test_bad_still_raises():
    resp = SimpleNamespace(result="BAD", lines=[b"no such message"])
    with pytest.raises(ValueError):
        await imap_idle.new_uids(_imap(resp), 0)


async def test_poll_does_not_search_an_empty_mailbox():
    fake = FakeIdleBridge()
    fake.add_box("Labels/Tom", [])
    await fake.start()
    imap = IMAPClient(Settings(username="u", password="p", imap_port=fake.port, imap_timeout=2,
                               _env_file=None))
    try:
        first = await imap_idle.poll_new_messages(imap, "Labels/Tom", None, None, 50)
        assert first["last_uid"] == 0
        second = await imap_idle.poll_new_messages(imap, "Labels/Tom", 0, first["uidvalidity"], 50)
        assert second["messages"] == [] and second["last_uid"] == 0 and not second["has_more"]
        assert not [line for _, line in fake.commands if "UID SEARCH" in line.upper()]
    finally:
        await imap.disconnect()
        await fake.stop()

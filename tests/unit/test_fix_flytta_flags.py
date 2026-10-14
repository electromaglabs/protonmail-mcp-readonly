"""IMAPClient.set_flags: UID:t måste finnas och STORE-svaret kontrolleras."""
import pytest

from tests.fix_flytta_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


async def test_sets_flag_on_existing_uid(imap_and_bridge):
    imap, bridge = imap_and_bridge
    bridge.add("INBOX", "42")
    assert await imap.set_flags("INBOX", "42", r"(\Seen)", add=True) is True
    assert bridge.sent("UID STORE") == [("UID STORE", "42", "+FLAGS", r"(\Seen)")]


async def test_removes_flag(imap_and_bridge):
    imap, bridge = imap_and_bridge
    bridge.add("INBOX", "42")
    await imap.set_flags("INBOX", "42", r"(\Seen)", add=False)
    assert bridge.sent("UID STORE") == [("UID STORE", "42", "-FLAGS", r"(\Seen)")]


async def test_unknown_uid_raises_without_store(imap_and_bridge):
    imap, bridge = imap_and_bridge
    with pytest.raises(ValueError, match="Inget meddelande med UID 99999 i INBOX"):
        await imap.set_flags("INBOX", "99999", r"(\Seen)", add=True)
    assert bridge.sent("UID STORE") == []


async def test_store_no_raises_with_server_text(imap_and_bridge):
    imap, bridge = imap_and_bridge
    bridge.add("INBOX", "42")
    bridge.refuse["STORE"] = "backend error"
    with pytest.raises(ValueError, match="backend error"):
        await imap.set_flags("INBOX", "42", r"(\Seen)", add=True)

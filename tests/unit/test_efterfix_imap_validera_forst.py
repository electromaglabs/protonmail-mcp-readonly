"""Ogiltiga mappnamn och UID avvisas innan något skickas till Bridge (T4).

Före fixen körde läsmetoderna _ensure_connected (NOOP, eller anslutning och
LOGIN) innan namnet validerades.
"""
import pytest

from tests.fix_flytta_bridge import make_client

BAD_MAILBOX = "INBOX\r\nA1 DELETE INBOX"


@pytest.fixture
def client(monkeypatch):
    imap, bridge = make_client(monkeypatch)
    return imap, bridge


CALLS = {
    "get_mailbox_status": lambda c, mb, uid: c.get_mailbox_status(mb),
    "list_messages": lambda c, mb, uid: c.list_messages(mb),
    "get_message": lambda c, mb, uid: c.get_message(mb, uid),
    "get_message_headers": lambda c, mb, uid: c.get_message_headers(mb, uid),
    "search_messages": lambda c, mb, uid: c.search_messages(mb, unseen=True),
    "set_flags": lambda c, mb, uid: c.set_flags(mb, uid, r"(\Seen)", add=True),
    "delete_message_permanent": lambda c, mb, uid: c.delete_message(mb, uid, permanent=True),
}


@pytest.mark.parametrize("name", sorted(CALLS))
async def test_bad_mailbox_rejected_before_any_command(client, name):
    imap, bridge = client
    with pytest.raises(ValueError, match="Ogiltigt mailbox-namn|Permanent radering"):
        await CALLS[name](imap, BAD_MAILBOX, "1")
    assert bridge.client.method_calls == []


@pytest.mark.parametrize("name", ["get_message", "get_message_headers", "set_flags", "delete_message_permanent"])
async def test_bad_uid_rejected_before_any_command(client, name):
    imap, bridge = client
    with pytest.raises(ValueError, match="Ogiltigt UID"):
        await CALLS[name](imap, "Trash", "1:*")
    assert bridge.client.method_calls == []

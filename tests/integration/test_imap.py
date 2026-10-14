"""Integrationstester för IMAPClient mot en riktig ProtonMail Bridge."""

import pytest

pytestmark = [pytest.mark.integration]


async def test_connect_disconnect(imap_client):
    """Verifiera att connect/disconnect fungerar utan fel."""
    # imap_client-fixturen har redan anslutit — om vi når hit lyckades connect
    assert imap_client._client is not None
    # disconnect sker i fixturen teardown


async def test_list_mailboxes(imap_client):
    """Verifiera att list_mailboxes returnerar minst en brevlåda (INBOX)."""
    mailboxes = await imap_client.list_mailboxes()
    assert isinstance(mailboxes, list)
    assert len(mailboxes) > 0
    names = [m["name"] for m in mailboxes]
    assert any("INBOX" in n.upper() for n in names)


async def test_list_messages(imap_client):
    """list_messages returnerar ett sidindelat kuvert, nyaste UID först."""
    result = await imap_client.list_messages("INBOX", page=1, page_size=5)
    assert set(result) == {"messages", "total", "page", "pages", "has_more"}
    messages = result["messages"]
    assert len(messages) <= 5
    for msg in messages:
        assert {"uid", "subject", "from", "flags"} <= set(msg)
    uids = [int(m["uid"]) for m in messages]
    assert uids == sorted(uids, reverse=True)


async def test_search_unseen(imap_client):
    """search_messages med unseen=True returnerar metadata-dicts utan \\Seen."""
    messages = await imap_client.search_messages("INBOX", unseen=True)
    assert isinstance(messages, list)
    for msg in messages:
        assert msg["uid"].isdigit()
        assert "\\Seen" not in msg["flags"]


async def test_reading_does_not_mark_as_seen(imap_client):
    """Att lista och öppna ett mejl får inte ändra dess flaggor."""
    listing = await imap_client.list_messages("INBOX", page=1, page_size=1)
    if not listing["messages"]:
        pytest.skip("INBOX är tom")
    uid = listing["messages"][0]["uid"]
    flags_before = listing["messages"][0]["flags"]

    assert await imap_client.get_message("INBOX", uid) is not None

    after = await imap_client.list_messages("INBOX", page=1, page_size=1)
    same = [m for m in after["messages"] if m["uid"] == uid]
    if same:
        assert same[0]["flags"] == flags_before

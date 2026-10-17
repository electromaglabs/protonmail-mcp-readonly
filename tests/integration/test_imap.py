"""Integration tests for IMAPClient against a real Proton Mail Bridge (needs .env)."""

import pytest

pytestmark = [pytest.mark.integration]


async def test_connect_disconnect(imap_client):
    assert imap_client._client is not None


async def test_list_mailboxes(imap_client):
    mailboxes = await imap_client.list_mailboxes()
    assert isinstance(mailboxes, list)
    assert len(mailboxes) > 0


async def test_list_messages(imap_client):
    mailboxes = await imap_client.list_mailboxes()
    result = await imap_client.list_messages(mailboxes[0]["name"], page=1, page_size=5)
    assert set(result) == {"messages", "total", "page", "pages", "has_more"}
    for msg in result["messages"]:
        assert "uid" in msg
        assert "subject" in msg


async def test_search_unseen(imap_client):
    mailboxes = await imap_client.list_mailboxes()
    results = await imap_client.search_messages(mailboxes[0]["name"], unseen=True)
    assert isinstance(results, list)
    for msg in results:
        assert msg["uid"].isdigit()


async def test_reading_does_not_mark_as_read(imap_client):
    """Fetching an unread message must leave it unread."""
    mailboxes = await imap_client.list_mailboxes()
    name = mailboxes[0]["name"]
    unread = await imap_client.search_messages(name, unseen=True)
    if not unread:
        pytest.skip("no unread message to test with")
    uid = unread[0]["uid"]
    assert await imap_client.get_message(name, uid) is not None
    still_unread = {m["uid"] for m in await imap_client.search_messages(name, unseen=True)}
    assert uid in still_unread

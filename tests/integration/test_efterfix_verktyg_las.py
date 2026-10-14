"""Läs-endast-integrationstester för kontrakten från buggfasen (efterfix-verktyg).

Bara LIST, STATUS, SELECT, SEARCH och FETCH (BODY.PEEK/FLAGS) — inget test
här ändrar flaggor, flyttar, raderar, skapar mappar eller skickar mejl.

Kör: uv run pytest tests/integration/test_efterfix_verktyg_las.py -m integration
"""
import re
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from protonmail_mcp.tools.messages import get_email_headers

pytestmark = [pytest.mark.integration]

# Unikt namn som säkert inte finns. Bara läsning: SELECT/STATUS på det skapar inget.
MISSING = f"Folders/efterfix-finns-inte-{uuid.uuid4().hex[:12]}"
_SWEDISH_WORD_RE = re.compile(r"\w*[åäöÅÄÖ]\w*")


async def test_select_of_missing_mailbox_raises(imap_client):
    """K6: SELECT av en mapp som inte finns ger fel, inte en tom lista."""
    with pytest.raises(ValueError, match="finns inte"):
        await imap_client.list_messages(MISSING, page=1, page_size=1)


async def test_client_recovers_after_failed_select(imap_client):
    """Efter ett misslyckat SELECT kastas anslutningen; nästa läsning går ändå."""
    with pytest.raises(ValueError):
        await imap_client.list_messages(MISSING, page=1, page_size=1)
    result = await imap_client.list_messages("INBOX", page=1, page_size=1)
    assert set(result) >= {"messages", "total"}


async def test_status_of_missing_mailbox_raises(imap_client):
    """STATUS som Bridge svarar NO på ger fel, inte {messages: 0, unseen: 0}."""
    with pytest.raises(ValueError, match="finns inte"):
        await imap_client.get_mailbox_status(MISSING)


async def test_list_mailboxes_entries_have_contract_keys(imap_client):
    """Varje mapp har name, type, selectable och special_use."""
    mailboxes = await imap_client.list_mailboxes()
    assert mailboxes
    for mb in mailboxes:
        assert {"name", "type", "selectable", "special_use"} <= set(mb), mb
        assert isinstance(mb["selectable"], bool)
    inbox = [mb for mb in mailboxes if mb["name"].upper() == "INBOX"]
    assert inbox and inbox[0]["selectable"] is True


async def test_search_with_swedish_characters_finds_known_subject(imap_client):
    """Ett ord med åäö ur ett ämne i INBOX ger träff på just det brevet."""
    known = None
    for page in (1, 2, 3):
        listing = await imap_client.list_messages("INBOX", page=page, page_size=100)
        for msg in listing["messages"]:
            words = [w for w in _SWEDISH_WORD_RE.findall(msg.get("subject") or "") if len(w) >= 3]
            if words:
                known = (msg["uid"], max(words, key=len))
                break
        if known or not listing["has_more"]:
            break
    if known is None:
        pytest.skip("Inget av de nyaste breven i INBOX har ett ämne med åäö")
    uid, word = known

    result = await imap_client.search_messages("INBOX", subject=word, max_results=1000)

    hits = result["messages"]
    assert hits, f"ingen träff för ett ord som finns i ämnet på UID {uid}"
    assert uid in [h["uid"] for h in hits]
    assert all(word.casefold() in (h.get("subject") or "").casefold() for h in hits)


async def test_get_email_headers_uses_underscore_keys(imap_client):
    """K6 (verktygslagret): headers har message_id/reply_to som get_email."""
    listing = await imap_client.list_messages("INBOX", page=1, page_size=1)
    if not listing["messages"]:
        pytest.skip("INBOX är tom")
    uid = listing["messages"][0]["uid"]
    ctx = MagicMock()
    ctx.request_context.lifespan_context = SimpleNamespace(imap=imap_client, smtp=None)

    headers = await get_email_headers(ctx, uid=uid, mailbox="INBOX")

    assert headers["mailbox"] == "INBOX"
    assert not [k for k in headers if "-" in k]
    assert "message_id" in headers

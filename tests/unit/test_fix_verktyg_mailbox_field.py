"""Enhetstester: verktygssvaren anger mailbox (fix-verktyg, N5).

UID gäller per mapp, så ett UID utan mapp är tvetydigt. Fältet läggs till
i verktygslagret, inte i imap_client.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.tools.messages import get_email, get_email_headers, list_emails
from protonmail_mcp.tools.search import search_emails


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    return ctx


def _imap(ctx):
    return ctx.request_context.lifespan_context.imap


class TestMailboxField:
    async def test_list_emails_tags_each_message_and_envelope(self, mock_ctx):
        _imap(mock_ctx).list_messages.return_value = {
            "messages": [{"uid": "2"}, {"uid": "1"}],
            "total": 2, "page": 1, "pages": 1, "has_more": False,
        }
        result = await list_emails(mock_ctx, mailbox="Starred")
        assert result["mailbox"] == "Starred"
        assert [m["mailbox"] for m in result["messages"]] == ["Starred", "Starred"]
        assert [m["uid"] for m in result["messages"]] == ["2", "1"]
        assert result["total"] == 2

    async def test_list_emails_empty_mailbox_still_names_mailbox(self, mock_ctx):
        _imap(mock_ctx).list_messages.return_value = {
            "messages": [], "total": 0, "page": 1, "pages": 0, "has_more": False,
        }
        result = await list_emails(mock_ctx, mailbox="Drafts")
        assert result["mailbox"] == "Drafts"
        assert result["messages"] == []

    async def test_search_emails_tags_each_hit(self, mock_ctx):
        _imap(mock_ctx).search_messages.return_value = {
            "messages": [{"uid": "5"}, {"uid": "3"}],
            "total": 2, "has_more": False, "complete": True, "note": None,
        }
        result = await search_emails(mock_ctx, mailbox="All Mail")
        assert result["mailbox"] == "All Mail"
        assert result["messages"] == [
            {"uid": "5", "mailbox": "All Mail"}, {"uid": "3", "mailbox": "All Mail"}]

    async def test_get_email_includes_mailbox(self, mock_ctx, sample_raw_email):
        _imap(mock_ctx).get_message.return_value = sample_raw_email
        result = await get_email(mock_ctx, uid="9", mailbox="Archive")
        assert result["mailbox"] == "Archive"
        assert result["subject"] == "Test subject"

    async def test_get_email_headers_includes_mailbox(self, mock_ctx):
        _imap(mock_ctx).get_message_headers.return_value = {"subject": "Hej"}
        result = await get_email_headers(mock_ctx, uid="9", mailbox="Archive")
        # efterfix-rensning (F2): get_email_headers har samma märkning som get_email
        assert result.pop("untrusted_content_notice")
        assert result.pop("sanitized") == {}
        assert result.pop("suspicious_content") == []
        assert result == {"subject": "Hej", "mailbox": "Archive"}

    async def test_does_not_mutate_imap_result(self, mock_ctx):
        hits = [{"uid": "5"}]
        _imap(mock_ctx).search_messages.return_value = {
            "messages": hits, "total": 1, "has_more": False, "complete": True, "note": None,
        }
        await search_emails(mock_ctx, mailbox="Starred")
        assert hits == [{"uid": "5"}]

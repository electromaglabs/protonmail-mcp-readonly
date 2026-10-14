"""Enhetstester: get_email/get_email_headers kastar fel för obefintligt UID (fix-verktyg, punkt 13)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.tools.messages import get_email, get_email_headers


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    return ctx


class TestNotFound:
    async def test_get_email_raises_with_uid_and_mailbox(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.get_message.return_value = None
        with pytest.raises(ValueError, match=r"^Inget meddelande med UID 42 i Labels/X"):
            await get_email(mock_ctx, uid="42", mailbox="Labels/X")

    async def test_get_email_headers_raises_with_uid_and_mailbox(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.get_message_headers.return_value = None
        with pytest.raises(ValueError, match=r"^Inget meddelande med UID 7 i INBOX"):
            await get_email_headers(mock_ctx, uid="7")

    async def test_get_email_headers_returns_dict_when_found(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.get_message_headers.return_value = {
            "subject": "Hej"
        }
        result = await get_email_headers(mock_ctx, uid="7")
        assert result["subject"] == "Hej"

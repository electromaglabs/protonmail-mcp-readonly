"""Enhetstester: get_email_headers byter bindestreck mot understreck (efterfix-verktyg, K6).

imap_client._parse_headers behåller headernamnen (message-id, reply-to).
Verktygslagret gör dem konsekventa med get_email (message_id, reply_to).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.tools.messages import get_email_headers


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    return ctx


async def test_keys_use_underscore(mock_ctx):
    mock_ctx.request_context.lifespan_context.imap.get_message_headers.return_value = {
        "from": "a@ex.se",
        "to": "b@ex.se",
        "cc": "c@ex.se",
        "subject": "Hej",
        "date": "Mon, 1 Jan 2026 10:00:00 +0100",
        "message-id": "<m@ex.se>",
        "reply-to": "r@ex.se",
    }
    result = await get_email_headers(mock_ctx, uid="5", mailbox="INBOX")
    # efterfix-rensning (F2): get_email_headers har samma märkning som get_email
    assert result.pop("untrusted_content_notice")
    assert result.pop("sanitized") == {}
    assert result.pop("suspicious_content") == []
    assert result == {
        "from": "a@ex.se",
        "to": "b@ex.se",
        "cc": "c@ex.se",
        "subject": "Hej",
        "date": "Mon, 1 Jan 2026 10:00:00 +0100",
        "message_id": "<m@ex.se>",
        "reply_to": "r@ex.se",
        "mailbox": "INBOX",
    }


async def test_docstring_keys_match_returned_keys(mock_ctx):
    mock_ctx.request_context.lifespan_context.imap.get_message_headers.return_value = {
        "message-id": "<m@ex.se>",
        "reply-to": "r@ex.se",
    }
    result = await get_email_headers(mock_ctx, uid="5", mailbox="INBOX")
    for key in result:
        assert key in get_email_headers.__doc__

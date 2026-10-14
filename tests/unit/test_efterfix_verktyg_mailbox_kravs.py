"""Enhetstester: skrivverktygen saknar standardmapp (efterfix-verktyg, F2).

UID gäller per mapp. Ett UID från Starred eller Labels/X som skickas utan
mailbox träffade tidigare ett annat brev i INBOX. Läsverktygen behåller INBOX.
"""
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.tools.manage import (
    delete_email,
    mark_email_read,
    mark_email_unread,
    move_email,
)
from protonmail_mcp.tools.messages import get_email, get_email_headers, list_emails
from protonmail_mcp.tools.search import search_emails

WRITE_TOOLS = [delete_email, move_email, mark_email_read, mark_email_unread]
READ_TOOLS = [get_email, get_email_headers, list_emails, search_emails]


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    return ctx


@pytest.mark.parametrize("tool", WRITE_TOOLS, ids=lambda t: t.__name__)
def test_write_tool_mailbox_has_no_default(tool):
    param = inspect.signature(tool).parameters["mailbox"]
    assert param.default is inspect.Parameter.empty


@pytest.mark.parametrize("tool", WRITE_TOOLS, ids=lambda t: t.__name__)
def test_write_tool_docstring_explains_uid_per_mailbox(tool):
    doc = tool.__doc__
    assert "gäller per mapp" in doc
    assert "standard: INBOX" not in doc


@pytest.mark.parametrize("tool", READ_TOOLS, ids=lambda t: t.__name__)
def test_read_tool_keeps_inbox_default(tool):
    assert inspect.signature(tool).parameters["mailbox"].default == "INBOX"


async def test_delete_email_without_mailbox_does_not_touch_inbox(mock_ctx):
    with pytest.raises(TypeError, match="mailbox"):
        await delete_email(mock_ctx, uid="14")
    mock_ctx.request_context.lifespan_context.imap.delete_message.assert_not_called()


async def test_mark_read_without_mailbox_does_not_touch_inbox(mock_ctx):
    with pytest.raises(TypeError, match="mailbox"):
        await mark_email_read(mock_ctx, uid="14")
    mock_ctx.request_context.lifespan_context.imap.set_flags.assert_not_called()


async def test_delete_email_permanent_still_keyword(mock_ctx):
    imap = mock_ctx.request_context.lifespan_context.imap
    imap.delete_message.return_value = True
    assert await delete_email(mock_ctx, uid="3", mailbox="Trash", permanent=True) is True
    imap.delete_message.assert_called_once_with("Trash", "3", permanent=True)

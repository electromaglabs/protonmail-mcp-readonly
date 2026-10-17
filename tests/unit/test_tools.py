"""Unit-tester för MCP tool-funktioner i tools/."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from protonmail_mcp.tools.mailboxes import list_mailboxes, get_mailbox_status
from protonmail_mcp.tools.messages import list_emails, get_email, get_email_headers
from protonmail_mcp.tools.search import search_emails


@pytest.fixture
def mock_ctx():
    """Mock Context with an AppContext (imap only: this fork has no SMTP)."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    return ctx


# --- mailboxes.py ---


class TestListMailboxes:
    async def test_delegates_to_imap(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.list_mailboxes.return_value = [
            {"name": "INBOX"}, {"name": "Sent"}
        ]
        result = await list_mailboxes(mock_ctx)
        mock_ctx.request_context.lifespan_context.imap.list_mailboxes.assert_called_once()
        assert result == [{"name": "INBOX"}, {"name": "Sent"}]


class TestGetMailboxStatus:
    async def test_delegates_with_mailbox_arg(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.get_mailbox_status.return_value = {
            "messages": 42, "unseen": 3
        }
        result = await get_mailbox_status(mock_ctx, mailbox="Drafts")
        mock_ctx.request_context.lifespan_context.imap.get_mailbox_status.assert_called_once_with("Drafts")
        assert result == {"messages": 42, "unseen": 3}

    async def test_default_mailbox_is_inbox(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.get_mailbox_status.return_value = {}
        await get_mailbox_status(mock_ctx)
        mock_ctx.request_context.lifespan_context.imap.get_mailbox_status.assert_called_once_with("INBOX")


# --- messages.py ---


class TestListEmails:
    async def test_delegates_with_page_args(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.list_messages.return_value = {
            "messages": [{"uid": "1"}], "total": 1, "page": 2, "pages": 3, "has_more": True
        }
        result = await list_emails(mock_ctx, mailbox="Sent", page=2, page_size=10)
        mock_ctx.request_context.lifespan_context.imap.list_messages.assert_called_once_with(
            "Sent", page=2, page_size=10
        )
        assert result["page"] == 2
        assert result["messages"] == [{"uid": "1"}]

    async def test_default_args(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.list_messages.return_value = {
            "messages": [], "total": 0, "page": 1, "pages": 0, "has_more": False
        }
        await list_emails(mock_ctx)
        mock_ctx.request_context.lifespan_context.imap.list_messages.assert_called_once_with(
            "INBOX", page=1, page_size=20
        )


class TestGetEmail:
    async def test_returns_none_when_raw_is_none(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.get_message.return_value = None
        result = await get_email(mock_ctx, uid="123", mailbox="INBOX")
        mock_ctx.request_context.lifespan_context.imap.get_message.assert_called_once_with("INBOX", "123")
        assert result is None

    async def test_returns_parsed_dict_when_mail_exists(self, mock_ctx, sample_raw_email):
        mock_ctx.request_context.lifespan_context.imap.get_message.return_value = sample_raw_email
        result = await get_email(mock_ctx, uid="456")
        assert isinstance(result, dict)
        assert result["subject"] == "Test subject"
        assert result["from"] == "sender@example.com"
        assert "Hello world!" in result["body_plain"]


# --- search.py ---


class TestSearchEmails:
    async def test_delegates_all_filter_params(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.search_messages.return_value = ["1", "2", "3"]
        result = await search_emails(
            mock_ctx,
            mailbox="INBOX",
            from_addr="alice@example.com",
            subject="hello",
            since="01-Jan-2024",
            before="01-Feb-2024",
            unseen=True,
        )
        mock_ctx.request_context.lifespan_context.imap.search_messages.assert_called_once_with(
            "INBOX",
            from_addr="alice@example.com",
            subject="hello",
            since="01-Jan-2024",
            before="01-Feb-2024",
            unseen=True,
        )
        assert result == ["1", "2", "3"]

    async def test_defaults_none_filters(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.search_messages.return_value = []
        await search_emails(mock_ctx)
        mock_ctx.request_context.lifespan_context.imap.search_messages.assert_called_once_with(
            "INBOX",
            from_addr=None,
            subject=None,
            since=None,
            before=None,
            unseen=None,
        )


# --- messages.py (get_email_headers) ---


class TestGetEmailHeaders:
    async def test_get_email_headers_delegates_to_imap(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.get_message_headers.return_value = {
            "from": "alice@example.com",
            "subject": "Hello",
            "message-id": "<abc@example.com>",
        }
        result = await get_email_headers(mock_ctx, uid="42", mailbox="INBOX")
        mock_ctx.request_context.lifespan_context.imap.get_message_headers.assert_called_once_with(
            "INBOX", "42"
        )
        assert result == {
            "from": "alice@example.com",
            "subject": "Hello",
            "message-id": "<abc@example.com>",
        }

    async def test_get_email_headers_returns_none_when_not_found(self, mock_ctx):
        mock_ctx.request_context.lifespan_context.imap.get_message_headers.return_value = None
        result = await get_email_headers(mock_ctx, uid="999")
        assert result is None


# --- read-only guarantees ---


class TestReadOnlyToolSet:
    """The server must expose the six read tools and nothing else."""

    EXPECTED = {
        "list_mailboxes",
        "get_mailbox_status",
        "list_emails",
        "get_email",
        "get_email_headers",
        "search_emails",
    }

    async def test_only_read_tools_are_registered(self):
        from protonmail_mcp.server import mcp

        tools = await mcp.list_tools()
        assert {t.name for t in tools} == self.EXPECTED

    async def test_every_tool_is_marked_read_only(self):
        from protonmail_mcp.server import mcp

        for tool in await mcp.list_tools():
            assert tool.annotations is not None, tool.name
            assert tool.annotations.readOnlyHint is True, tool.name

    def test_write_modules_are_gone(self):
        import importlib

        for name in ("smtp_client", "tools.send", "tools.reply", "tools.manage", "tools.folders"):
            with pytest.raises(ModuleNotFoundError):
                importlib.import_module(f"protonmail_mcp.{name}")

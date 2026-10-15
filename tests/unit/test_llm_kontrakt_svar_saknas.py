"""Enhetstester: reply_to_email/forward_email kastar fel för obefintligt UID (llm-kontrakt, K1)."""
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.tools import reply


@pytest.fixture
def ctx():
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    ctx.request_context.lifespan_context.imap.get_message.return_value = None
    ctx.request_context.lifespan_context.smtp = AsyncMock()
    return ctx


async def test_reply_raises_not_found(ctx):
    with pytest.raises(ValueError, match=r"Inget meddelande med UID 99 i Archive\. UID:n gäller per mapp"):
        await reply.reply_to_email(ctx, uid="99", body="Hej", mailbox="Archive")
    ctx.request_context.lifespan_context.smtp.send_email.assert_not_called()


async def test_forward_raises_not_found(ctx):
    with pytest.raises(ValueError, match=r"Inget meddelande med UID 99 i Archive\. UID:n gäller per mapp"):
        await reply.forward_email(ctx, uid="99", to="anna@example.com", mailbox="Archive")
    ctx.request_context.lifespan_context.smtp.send_email.assert_not_called()


@pytest.mark.parametrize("tool", [reply.reply_to_email, reply.forward_email])
def test_docstring_documents_the_error(tool):
    doc = inspect.getdoc(tool)
    assert "Inget meddelande med UID" in doc

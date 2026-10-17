from mcp.server.fastmcp import Context

from ..server import mcp
from . import READ_ONLY, _get_app


@mcp.tool(annotations=READ_ONLY)
async def list_mailboxes(ctx: Context) -> list[dict]:
    """List the folders and labels this server is allowed to read."""
    app = _get_app(ctx)
    return await app.imap.list_mailboxes()


@mcp.tool(annotations=READ_ONLY)
async def get_mailbox_status(ctx: Context, mailbox: str = "INBOX") -> dict:
    """Get the number of messages and unread messages in a folder.

    Args:
        mailbox: Folder name (default: INBOX)
    """
    app = _get_app(ctx)
    return await app.imap.get_mailbox_status(mailbox)

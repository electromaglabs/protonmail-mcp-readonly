from mcp.server.fastmcp import Context

from ..server import mcp
from . import READ_ONLY, _get_app


@mcp.tool(annotations=READ_ONLY)
async def search_emails(
    ctx: Context,
    mailbox: str = "INBOX",
    from_addr: str | None = None,
    subject: str | None = None,
    since: str | None = None,
    before: str | None = None,
    unseen: bool | None = None,
) -> list[dict]:
    """Search emails in one folder with filters.

    Args:
        mailbox: Folder to search (default: INBOX)
        from_addr: Filter on sender address (single line, max 200 characters)
        subject: Filter on subject (single line, max 200 characters)
        since: Only emails on or after this date (YYYY-MM-DD)
        before: Only emails before this date (YYYY-MM-DD)
        unseen: true = unread only, false = read only, null = all

    Returns:
        List of metadata dicts (uid, subject, from, date, flags) for matching emails
    """
    app = _get_app(ctx)
    return await app.imap.search_messages(
        mailbox,
        from_addr=from_addr,
        subject=subject,
        since=since,
        before=before,
        unseen=unseen,
    )

from mcp.server.fastmcp import Context

from ..server import mcp
from ..email_parser import parse_email
from . import READ_ONLY, _get_app


@mcp.tool(annotations=READ_ONLY)
async def get_email_headers(
    ctx: Context,
    uid: str,
    mailbox: str = "INBOX",
) -> dict | None:
    """Get the headers of an email without loading the body. Does not mark it as read.

    Args:
        uid: The email's UID
        mailbox: Folder name (default: INBOX)

    Returns:
        Dict with from, to, cc, subject, date, message-id, reply-to, or None if not found
    """
    app = _get_app(ctx)
    return await app.imap.get_message_headers(mailbox, uid)


@mcp.tool(annotations=READ_ONLY)
async def list_emails(
    ctx: Context,
    mailbox: str = "INBOX",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List emails in a folder with metadata, newest first (page-based).

    Args:
        mailbox: Folder name (default: INBOX)
        page: Page number, starting at 1 (default: 1)
        page_size: Emails per page, 1-100 (default: 20)

    Returns:
        dict with keys: messages, total, page, pages, has_more
    """
    app = _get_app(ctx)
    return await app.imap.list_messages(mailbox, page=page, page_size=page_size)


@mcp.tool(annotations=READ_ONLY)
async def get_email(
    ctx: Context,
    uid: str,
    mailbox: str = "INBOX",
    body_format: str = "text",
    max_length: int | None = 500,
) -> dict | None:
    """Get the content of an email by UID. Does not mark it as read.

    Attachments are listed by name, type and size only; their content is never returned.

    Args:
        uid: The email's UID
        mailbox: Folder name (default: INBOX)
        body_format: "text" (plain text, default), "stripped" (plain text without
            quoted replies and signature), or "full" (plain text, raw HTML and all
            headers, with no length limit)
        max_length: Maximum characters of body text for "text" and "stripped"
            (default: 500). null = no limit. Ignored for "full".
    """
    app = _get_app(ctx)
    raw = await app.imap.get_message(mailbox, uid)
    if raw is None:
        return None
    return parse_email(raw, body_format=body_format, max_length=max_length)

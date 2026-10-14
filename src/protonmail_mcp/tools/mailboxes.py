from mcp.server.fastmcp import Context

from ..server import mcp
from . import _get_app


@mcp.tool()
async def list_mailboxes(ctx: Context) -> list[dict]:
    """Lista alla mappar/etiketter i brevlådan.

    Varje post har:
        name: läsbart namn (å/ä/ö avkodade). Skicka det oförändrat till andra
            verktyg; etiketter med "/" i namnet har det escapat som "\\/".
        type: "system" (INBOX, Drafts, Sent, Starred, Archive, Spam, Trash,
            All Mail), "folder" (Folders/*), "label" (Labels/*) eller
            "container" (behållare som Folders och Labels, går inte att öppna).
        selectable: False för behållare; de innehåller inga mejl.
        special_use: "\\Drafts", "\\Sent", "\\All", "\\Archive", "\\Junk",
            "\\Trash", "\\Flagged" eller None.
    """
    app = _get_app(ctx)
    return await app.imap.list_mailboxes()


@mcp.tool()
async def get_mailbox_status(ctx: Context, mailbox: str = "INBOX") -> dict:
    """Hämta antal meddelanden och olästa i en mapp.

    Args:
        mailbox: Mappnamn (standard: INBOX)
    """
    app = _get_app(ctx)
    return await app.imap.get_mailbox_status(mailbox)

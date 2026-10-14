from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from ..server import mcp
from . import _get_app
from ._types import OptionalStr
from .messages import _with_mailbox


@mcp.tool()
async def search_emails(
    ctx: Context,
    mailbox: str = "INBOX",
    from_addr: OptionalStr = None,
    subject: OptionalStr = None,
    since: OptionalStr = None,
    before: OptionalStr = None,
    unseen: bool | None = None,
    max_results: Annotated[int, Field(ge=1, le=200)] = 50,
) -> list[dict]:
    """Sök e-post med filter.

    Args:
        mailbox: Mappnamn att söka i (standard: INBOX)
        from_addr: Filtrera på avsändaradress
        subject: Filtrera på ämnesrad
        since: Filtrera e-post efter datum (format: YYYY-MM-DD eller DD-Mon-YYYY)
        before: Filtrera e-post före datum (format: YYYY-MM-DD eller DD-Mon-YYYY)
        unseen: True=bara olästa, False=bara lästa, None=alla
        max_results: Högsta antal träffar, 1–200 (standard: 50). De nyaste returneras.

    Returns:
        Lista med metadata-dicts (uid, mailbox, subject, from, date, flags) för matchande
        e-post. UID:t gäller bara i den mapp som anges i mailbox.
    """
    app = _get_app(ctx)
    hits = await app.imap.search_messages(
        mailbox,
        from_addr=from_addr,
        subject=subject,
        since=since,
        before=before,
        unseen=unseen,
        max_results=max_results,
    )
    return _with_mailbox(hits, mailbox)

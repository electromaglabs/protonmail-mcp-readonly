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
) -> dict:
    """Sök e-post med filter.

    Ämne och avsändare jämförs mot avkodade headers, så sökningar med å, ä och ö
    fungerar. Det görs lokalt för de 1000 nyaste brev som matchar övriga villkor;
    complete=False och note talar om när inte alla brev kunde kontrolleras.

    Args:
        mailbox: Mappnamn att söka i (standard: INBOX)
        from_addr: Filtrera på avsändare (adress eller namn, delsträng)
        subject: Filtrera på ämnesrad (delsträng, skiftlägesoberoende)
        since: Filtrera e-post efter datum (format: YYYY-MM-DD eller DD-Mon-YYYY)
        before: Filtrera e-post före datum (format: YYYY-MM-DD eller DD-Mon-YYYY)
        unseen: True=bara olästa, False=bara lästa, None=alla
        max_results: Högsta antal träffar, 1–200 (standard: 50). De nyaste returneras.

    Returns:
        dict med nycklar: mailbox, messages, total, has_more, complete, note.
        messages är metadata-dicts (uid, mailbox, subject, from, date, flags), nyaste
        först. total är antal hittade träffar (en undre gräns när complete är False).
        UID:t gäller bara i den mapp som anges i mailbox.
    """
    app = _get_app(ctx)
    result = await app.imap.search_messages(
        mailbox,
        from_addr=from_addr,
        subject=subject,
        since=since,
        before=before,
        unseen=unseen,
        max_results=max_results,
    )
    return {
        **result,
        "mailbox": mailbox,
        "messages": _with_mailbox(result["messages"], mailbox),
    }

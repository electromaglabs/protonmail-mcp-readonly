from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from ..imap_threads import get_thread as fetch_thread
from ..server import mcp
from . import _get_app


@mcp.tool()
async def get_thread(
    ctx: Context,
    uid: str,
    mailbox: str,
    max_messages: Annotated[int, Field(ge=1, le=200, strict=True)] = 50,
) -> dict:
    """Hämta hela konversationen (tråden) som ett mejl ingår i.

    Bridge har ingen trådfunktion, så konversationen byggs av mejlens
    Message-ID, In-Reply-To och References: alla mejl i All Mail som hör till
    samma kedja, både mottagna och skickade. Inget ändras — inga mejl
    markeras som lästa. Brödtexten hämtas inte; läs varje mejl med
    get_email(uid, mailbox="All Mail").

    Mejl som svarar utan In-Reply-To/References (t.ex. ett nytt mejl med samma
    ämne) kommer inte med. Sökningen i All Mail tar några sekunder per runda
    (3–8 s på ett konto med ~30 000 mejl), och görs i högst sex rundor.

    Args:
        uid: Mejlets UID i mailbox
        mailbox: Mappen där UID:t gäller (t.ex. INBOX)
        max_messages: Högst så många mejl, 1–200 (standard: 50). Är
            konversationen längre returneras startmejlet och de senaste.

    Returns:
        dict med mailbox ("All Mail"), messages (äldst först; uid i All Mail,
        mailbox, from, to, cc, subject, date, message_id, in_reply_to, flags),
        total (antal hittade mejl), complete (False om taket nåddes eller
        startmejlet saknar Message-ID) och note.

    Raises:
        ValueError: ogiltigt UID eller mappnamn, mappen finns inte, inget mejl
            med UID:t i mappen, eller Bridge avvisade sökningen.
    """
    app = _get_app(ctx)
    return await fetch_thread(app.imap, uid, mailbox, max_messages=max_messages)

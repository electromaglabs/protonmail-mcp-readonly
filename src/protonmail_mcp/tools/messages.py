from typing import Annotated, Literal

from mcp.server.fastmcp import Context
from pydantic import Field

from ..server import mcp
from ..email_parser import parse_email
from . import _get_app


def _with_mailbox(messages: list[dict], mailbox: str) -> list[dict]:
    """Märk varje meddelande med mappen — UID är bara unikt inom en mapp."""
    return [{**m, "mailbox": mailbox} for m in messages]


def _not_found(uid: str, mailbox: str) -> ValueError:
    # UID gäller per mapp — ett UID från en annan mapp är det vanligaste skälet
    return ValueError(
        f"Inget meddelande med UID {uid} i {mailbox}. "
        "UID:n gäller per mapp — kontrollera att mailbox är samma mapp som UID:t kom från."
    )


@mcp.tool()
async def get_email_headers(
    ctx: Context,
    uid: str,
    mailbox: str = "INBOX",
) -> dict:
    """Hämta headers för ett e-post utan att ladda body (snabb operation).

    Args:
        uid: E-postets UID
        mailbox: Mappnamn (standard: INBOX)

    Returns:
        Dict med from, to, cc, subject, date, message_id, reply_to och mailbox.
        Kastar fel om det inte finns något meddelande med UID:t i mappen.
    """
    app = _get_app(ctx)
    headers = await app.imap.get_message_headers(mailbox, uid)
    if headers is None:
        raise _not_found(uid, mailbox)
    # Samma nyckelnamn som get_email: message-id → message_id, reply-to → reply_to
    return {**{k.replace("-", "_"): v for k, v in headers.items()}, "mailbox": mailbox}


@mcp.tool()
async def list_emails(
    ctx: Context,
    mailbox: str = "INBOX",
    page: Annotated[int, Field(ge=1)] = 1,
    page_size: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict:
    """Lista e-post i en mapp med metadata (sidbaserad paginering).

    Args:
        mailbox: Mappnamn (standard: INBOX)
        page: Sidnummer, 1-baserat (standard: 1). En sida förbi slutet ger en tom lista.
        page_size: Antal e-post per sida, 1–100 (standard: 20)

    Returns:
        dict med nycklar: mailbox, messages, total, page, pages, has_more.
        Varje meddelande har mailbox — UID:t gäller bara i den mappen.
    """
    app = _get_app(ctx)
    result = await app.imap.list_messages(mailbox, page=page, page_size=page_size)
    return {
        **result,
        "mailbox": mailbox,
        "messages": _with_mailbox(result["messages"], mailbox),
    }


@mcp.tool()
async def get_email(
    ctx: Context,
    uid: str,
    mailbox: str = "INBOX",
    body_format: Literal["text", "full", "stripped"] = "text",
    max_length: Annotated[int, Field(ge=0)] | None = 500,
) -> dict:
    """Hämta fullständigt innehåll för ett e-post via UID.

    Args:
        uid: E-postets UID
        mailbox: Mappnamn (standard: INBOX)
        body_format: Format för body — "text" (plain text, default), "full" (rå body utan
            trunkering), eller "stripped" (text utan citat och signaturblock)
        max_length: Max antal tecken i body (standard: 500). None = ingen trunkering.
            Ignoreras för body_format="full".

    Returns:
        Det parsade meddelandet, inklusive mailbox som UID:t gäller i.
    """
    app = _get_app(ctx)
    raw = await app.imap.get_message(mailbox, uid)
    if raw is None:
        raise _not_found(uid, mailbox)
    return {**parse_email(raw, body_format=body_format, max_length=max_length), "mailbox": mailbox}

"""Utkast som säkert arbetsflöde: Claude skriver, människan granskar och skickar.

Utkasten läggs i Drafts med IMAP APPEND. Bridge gör dem till riktiga utkast i
Proton, där de kan läsas, ändras och skickas. Befintliga utkast listas med
list_emails(mailbox="Drafts") och läses med get_email(uid, mailbox="Drafts").
"""
from collections.abc import Sequence
from email.message import EmailMessage, Message
from typing import Any

from mcp.server.fastmcp import Context

from .. import imap_drafts
from ..server import mcp
from ..smtp_client import (
    _build_message,
    _normalize_recipients,
    _to_address,
    _validate_email_addr,
    _validate_subject,
)
from . import _get_app
from ._types import OptionalStr

DRAFTS = imap_drafts.DRAFTS


def _build_draft(
    app,
    *,
    to: str | Sequence[str] | None,
    subject: str,
    body: str,
    body_html: str | None = None,
    cc: str | Sequence[str] | None = None,
    bcc: str | Sequence[str] | None = None,
    reply_to: str | None = None,
    additional_headers: dict[str, str] | None = None,
    attachments: Sequence[Message] | None = None,
    inline_parts: Sequence[Message] | None = None,
) -> EmailMessage:
    """Bygg utkastet med samma validering och byggare som send_email.

    Skillnaden mot ett skickat mejl är att Bcc sparas som header: utkastet
    ska visa de hemliga mottagarna vid granskningen, och send_draft läser dem
    därifrån (och tar bort headern ur det som skickas).
    """
    _validate_subject(subject)
    to_list = _normalize_recipients(to)
    cc_list = _normalize_recipients(cc)
    bcc_list = _normalize_recipients(bcc)
    for addr in to_list + cc_list + bcc_list:
        _validate_email_addr(addr)
    if reply_to:
        _validate_email_addr(reply_to)

    msg = _build_message(
        from_addr=app.smtp.account_address,
        to_list=to_list,
        subject=subject,
        body=body,
        body_html=body_html,
        cc_list=cc_list,
        reply_to=reply_to,
        additional_headers=additional_headers,
        attachments=attachments,
        inline_parts=inline_parts,
    )
    if bcc_list:
        msg["Bcc"] = [_to_address(a) for a in bcc_list]
    return msg


def _draft_result(uid: str | None, msg: EmailMessage) -> dict[str, Any]:
    result: dict[str, Any] = {"uid": uid, "mailbox": DRAFTS, "message_id": msg["Message-ID"]}
    if uid is None:
        result["note"] = (
            "Utkastet sparades, men Bridge angav inget UID. Hitta det med "
            'list_emails(mailbox="Drafts").'
        )
    return result


async def _save(app, msg: EmailMessage) -> dict[str, Any]:
    uid = await imap_drafts.append_draft(app.imap, msg.as_bytes(), msg["Message-ID"])
    return _draft_result(uid, msg)


@mcp.tool()
async def create_draft(
    ctx: Context,
    to: str | list[str],
    subject: str,
    body: str,
    body_html: OptionalStr = None,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    reply_to: OptionalStr = None,
) -> dict:
    """Skapa ett utkast i Drafts i stället för att skicka. Ingenting skickas.

    Mejlet byggs exakt som send_email bygger det (samma adressvalidering,
    kodning, Message-ID och avsändare) och sparas i Drafts. Bridge gör det till
    ett riktigt utkast i Proton, som du kan granska, ändra och skicka i Protons
    appar — eller skicka härifrån med send_draft när det är godkänt. Hemliga
    kopior (bcc) sparas i utkastet så att de syns vid granskningen.
    Befintliga utkast listas med list_emails(mailbox="Drafts").

    Args:
        to: Mottagaradress(er) — sträng eller lista
        subject: Ämnesrad
        body: Brödtext i klartext
        body_html: Valfri HTML-version av brödtexten
        cc: Kopia-adress(er)
        bcc: Hemlig kopia-adress(er)
        reply_to: Svarsadress

    Returns:
        {"uid", "mailbox": "Drafts", "message_id"}. uid är utkastets UID i
        Drafts (använd det med update_draft, send_draft eller get_email).
        Kan Bridge inte ange UID:t blir det null och "note" förklarar.

    Raises:
        ValueError: ogiltig adress eller ämnesrad (inget sparas), eller om
            Bridge vägrar spara utkastet.
    """
    app = _get_app(ctx)
    msg = _build_draft(
        app, to=to, subject=subject, body=body, body_html=body_html,
        cc=cc, bcc=bcc, reply_to=reply_to,
    )
    return await _save(app, msg)

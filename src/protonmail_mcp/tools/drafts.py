"""Utkast som säkert arbetsflöde: Claude skriver, människan granskar och skickar.

Utkasten läggs i Drafts med IMAP APPEND. Bridge gör dem till riktiga utkast i
Proton, där de kan läsas, ändras och skickas. Befintliga utkast listas med
list_emails(mailbox="Drafts") och läses med get_email(uid, mailbox="Drafts").
"""
import email
import email.policy
import logging
from collections.abc import Sequence
from email.message import EmailMessage, Message
from typing import Any, Literal

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
from .reply import build_forward, build_reply

logger = logging.getLogger(__name__)

DRAFTS = imap_drafts.DRAFTS


def _not_found(uid: str, mailbox: str) -> ValueError:
    return ValueError(
        f"Inget meddelande med UID {uid} i {mailbox}. "
        "UID:n gäller per mapp — kontrollera att mailbox är samma mapp som UID:t kom från."
    )


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


@mcp.tool()
async def create_reply_draft(
    ctx: Context,
    uid: str,
    mailbox: str,
    body: str,
    reply_all: bool = False,
    body_html: OptionalStr = None,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    quote_original: bool = True,
) -> dict:
    """Skapa ett svar som utkast i Drafts i stället för att skicka det. Ingenting skickas.

    Svaret byggs exakt som reply_to_email bygger det: samma mottagare (Reply-To,
    annars From; svara alla tar med To och Cc utom ditt eget konto), ett enda
    "Re: ", In-Reply-To och References så att det hamnar i rätt tråd, och
    originalet citerat under texten. Utkastet kan granskas och skickas i
    Proton, eller skickas härifrån med send_draft när det är godkänt.

    Args:
        uid: UID för mejlet att svara på
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp.
        body: Svarstexten i klartext
        reply_all: Svara alla — ta även med originalets To och Cc
        body_html: Valfri HTML-version av svarstexten
        cc: Ytterligare kopia-adress(er)
        bcc: Hemlig kopia-adress(er) (sparas i utkastet)
        quote_original: Citera originalet under svaret (standard: True)

    Returns:
        {"uid", "mailbox": "Drafts", "message_id"} för utkastet.

    Raises:
        ValueError: originalet finns inte, ogiltig adress, eller om Bridge
            vägrar spara utkastet.
    """
    app = _get_app(ctx)
    fields = await build_reply(
        app, uid, mailbox, body,
        body_html=body_html, reply_all=reply_all, cc=cc, quote_original=quote_original,
    )
    if fields is None:
        raise _not_found(uid, mailbox)
    return await _save(app, _build_draft(app, **fields, bcc=bcc))


@mcp.tool()
async def create_forward_draft(
    ctx: Context,
    uid: str,
    mailbox: str,
    to: str | list[str],
    body: str = "",
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
) -> dict:
    """Skapa en vidarebefordran som utkast i Drafts i stället för att skicka den.

    Byggs exakt som forward_email: "Fwd: "-ämne, originalet inline under ett
    rubrikblock (text och HTML) och alla bilagor och inbäddade bilder med.
    Ingenting skickas; granska i Proton eller skicka med send_draft.

    Args:
        uid: UID för mejlet att vidarebefordra
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp.
        to: Mottagaradress(er)
        body: Valfri text ovanför det vidarebefordrade meddelandet
        cc: Kopia-adress(er)
        bcc: Hemlig kopia-adress(er) (sparas i utkastet)

    Returns:
        {"uid", "mailbox": "Drafts", "message_id"} för utkastet.

    Raises:
        ValueError: originalet finns inte, ogiltig adress, eller om Bridge
            vägrar spara utkastet.
    """
    app = _get_app(ctx)
    fields = await build_forward(app, uid, mailbox, to, body, cc=cc)
    if fields is None:
        raise _not_found(uid, mailbox)
    return await _save(app, _build_draft(app, **fields, bcc=bcc))


@mcp.tool()
async def update_draft(
    ctx: Context,
    uid: str,
    mailbox: Literal["Drafts"],
    to: str | list[str],
    subject: str,
    body: str,
    body_html: OptionalStr = None,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    reply_to: OptionalStr = None,
) -> dict:
    """Ersätt ett utkast i Drafts med en ny version. Ingenting skickas.

    Den nya versionen byggs som create_draft (alla fält anges på nytt) och
    sparas först; därefter raderas det gamla utkastet permanent (UID STORE
    \\Deleted + UID EXPUNGE på just det UID:t). Misslyckas sparandet ligger det
    gamla utkastet kvar orört. Utkastet får ett nytt UID och ett nytt
    Message-ID. Bara utkast i Drafts kan uppdateras; hitta dem med
    list_emails(mailbox="Drafts").

    Args:
        uid: Utkastets UID i Drafts (från create_draft eller list_emails)
        mailbox: Alltid "Drafts" — anges för att bekräfta att UID:t kommer därifrån
        to: Mottagaradress(er) — sträng eller lista
        subject: Ämnesrad
        body: Brödtext i klartext
        body_html: Valfri HTML-version av brödtexten
        cc: Kopia-adress(er)
        bcc: Hemlig kopia-adress(er)
        reply_to: Svarsadress

    Returns:
        {"uid", "mailbox": "Drafts", "message_id", "replaced_uid"} där uid är
        det nya utkastets UID och replaced_uid det raderade.

    Raises:
        ValueError: utkastet finns inte i Drafts, ogiltig adress eller
            ämnesrad (inget ändras), Bridge vägrar spara (det gamla ligger
            kvar), eller det gamla gick inte att radera (båda ligger kvar;
            felet anger UID:n).
    """
    if mailbox != DRAFTS:
        raise ValueError(f"Bara utkast i {DRAFTS} kan uppdateras, inte i {mailbox!r}")
    app = _get_app(ctx)
    msg = _build_draft(
        app, to=to, subject=subject, body=body, body_html=body_html,
        cc=cc, bcc=bcc, reply_to=reply_to,
    )
    new_uid = await imap_drafts.replace_draft(app.imap, uid, msg.as_bytes(), msg["Message-ID"])
    return {**_draft_result(new_uid, msg), "replaced_uid": uid}


@mcp.tool()
async def send_draft(
    ctx: Context,
    uid: str,
    mailbox: Literal["Drafts"],
) -> dict:
    """Skicka ett utkast ur Drafts exakt som det ligger där, och ta sedan bort det.

    Använd först när utkastet är granskat och godkänt. Utkastet hämtas ur
    Drafts (med eventuella ändringar som gjorts i Proton) och skickas över
    SMTP till alla adresser i To, Cc och Bcc. Bcc-headern tas bort ur det
    som skickas, så de hemliga mottagarna syns inte för de andra. Efter
    skicket raderas utkastet permanent ur Drafts; Bridge lägger det skickade
    mejlet i Sent. Hitta utkast med list_emails(mailbox="Drafts").

    Misslyckas skicket ligger utkastet kvar orört. Vägrar servern bara några
    mottagare har mejlet ändå gått till de övriga: felet anger vilka, och
    utkastet ligger kvar — skicka då inte om det till alla.

    Args:
        uid: Utkastets UID i Drafts (från create_draft eller list_emails)
        mailbox: Alltid "Drafts" — anges för att bekräfta att UID:t kommer därifrån

    Returns:
        {"sent": True, "message_id", "draft_deleted"}. Gick utkastet inte att
        ta bort efter skicket är draft_deleted False och "warning" förklarar —
        mejlet HAR då skickats och ska inte skickas igen.

    Raises:
        ValueError: utkastet finns inte i Drafts, saknar mottagare eller har
            en ogiltig adress (inget skickas).
        SMTPPartialDeliveryError: servern vägrade några av mottagarna.
    """
    if mailbox != DRAFTS:
        raise ValueError(f"Bara utkast i {DRAFTS} kan skickas, inte i {mailbox!r}")
    app = _get_app(ctx)
    raw = await app.imap.get_message(DRAFTS, uid)
    if raw is None:
        raise ValueError(
            f"Inget utkast med UID {uid} i {DRAFTS}. "
            'Hitta utkasten med list_emails(mailbox="Drafts").'
        )
    msg = email.message_from_bytes(raw, policy=email.policy.SMTP)
    # Fel här (även delvis leverans) går vidare och utkastet lämnas kvar
    await app.smtp.send_prepared_message(msg)

    result: dict[str, Any] = {
        "sent": True,
        "message_id": msg["Message-ID"],
        "draft_deleted": True,
    }
    try:
        await app.imap.delete_message(DRAFTS, uid, permanent=True)
    except Exception as exc:  # mejlet är redan skickat — det får inte se ut som ett fel
        logger.warning("Utkastet UID %s skickades men kunde inte tas bort: %s", uid, exc)
        result["draft_deleted"] = False
        result["warning"] = (
            f"Mejlet skickades, men utkastet (UID {uid}) kunde inte tas bort ur "
            f"{DRAFTS}: {exc}. Skicka inte igen — ta bort utkastet med "
            f'delete_email(uid="{uid}", mailbox="Drafts", permanent=True).'
        )
    return result

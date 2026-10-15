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
from .reply import _forward_parts, _msg_ids, _parse_original, build_forward, build_reply

logger = logging.getLogger(__name__)

DRAFTS = imap_drafts.DRAFTS
# Bridge visar Proton-ID:n som <id@protonmail.internalid> (pkg/message/build.go)
_INTERNAL_ID_DOMAIN = "protonmail.internalid"


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


def _part_name(part: Message) -> str:
    return part.get_filename() or part.get_content_type()


def _kept_from_old(old_raw: bytes, body_html: str | None) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Det som update_draft för över från det gamla utkastet till det nya.

    Returnerar (argument till _build_draft, sammanfattning för svaret):
    - In-Reply-To och References, bara som rena <msg-id> (inget annat ur
      råvärdet kan följa med in i det nya utkastets headers). Det gamla
      utkastets egen interna Proton-referens (<X-Pm-Internal-Id@protonmail.
      internalid>, som Bridge lägger till när utkastet hämtas) tas bort: den
      pekar på det ersatta utkastet. Övriga internalid-referenser behålls —
      Bridge hittar originalet (och tråden) med dem vid skicket.
    - Alla delar som inte är brödtexten (bilagor, bifogade mejl, inbäddade
      bilder), oförändrade. Inbäddade bilder som den nya HTML-versionen pekar
      på med cid: läggs bredvid den; övriga blir vanliga bilagor.
    """
    old = _parse_original(old_raw)
    own_ids = {
        f"<{value.strip()}@{_INTERNAL_ID_DOMAIN}>".lower()
        for key, value in old.raw_items()
        if key.lower() == "x-pm-internal-id" and str(value).strip()
    }
    headers: dict[str, str] = {}
    in_reply_to = _msg_ids(old, "In-Reply-To")
    references = [r for r in _msg_ids(old, "References") if r.lower() not in own_ids]
    if in_reply_to:
        headers["In-Reply-To"] = " ".join(in_reply_to)
    if references:
        headers["References"] = " ".join(references)

    body_parts = [p for p in (old.get_body(("plain",)), old.get_body(("html",))) if p is not None]
    inline, attached = _forward_parts(old, body_parts, body_html or "")
    fields = {
        "additional_headers": headers or None,
        "attachments": attached or None,
        "inline_parts": inline or None,
    }
    summary = {
        "kept_headers": list(headers),
        "kept_attachments": [_part_name(p) for p in attached + inline],
    }
    return fields, summary


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

    ERSÄTTS (anges på nytt i varje anrop, som i create_draft): to, subject,
    body, body_html, cc, bcc och reply_to. Ett fält som utelämnas blir tomt —
    ange alltså cc, bcc och body_html igen om de ska vara kvar. Avsändare,
    Date och Message-ID blir nya.

    BEHÅLLS från det gamla utkastet:
    - In-Reply-To och References, så att ett svarsutkast (create_reply_draft)
      stannar i tråden;
    - alla delar som inte är brödtext: bilagor, bifogade mejl och inbäddade
      bilder (t.ex. originalets bilagor i ett vidarebefordringsutkast),
      byte för byte. Inbäddade bilder som body_html pekar på med cid: visas
      i HTML-versionen; utan body_html blir de vanliga bilagor.

    Den nya versionen sparas först. Därefter flyttas det gamla utkastet till
    Trash (UID MOVE) — det raderas inte, så det går att återställa om något
    blev fel. Misslyckas sparandet ligger det gamla utkastet kvar orört.
    Utkastet får ett nytt UID. Bara utkast i Drafts kan uppdateras; hitta dem
    med list_emails(mailbox="Drafts") och läs dem med get_email.

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
        {"uid", "mailbox": "Drafts", "message_id", "replaced_uid",
        "replaced_moved_to": "Trash", "kept_headers", "kept_attachments"}
        där uid är det nya utkastets UID, replaced_uid det gamla (som nu
        ligger i Trash), kept_headers de trådheaders som fördes över och
        kept_attachments filnamnen (eller MIME-typen) för de delar som följde med.

    Raises:
        ValueError: utkastet finns inte i Drafts, ogiltig adress eller
            ämnesrad (inget ändras), Bridge vägrar spara (det gamla ligger
            kvar), eller det gamla gick inte att flytta till Trash — nekat,
            timeout eller bruten anslutning. Då är det nya utkastet redan
            sparat: felet anger dess UID och Message-ID samt det gamla UID:t.
            Kör då INTE update_draft igen (det skapar ett utkast till).
    """
    if mailbox != DRAFTS:
        raise ValueError(f"Bara utkast i {DRAFTS} kan uppdateras, inte i {mailbox!r}")
    app = _get_app(ctx)
    old_raw = await app.imap.get_message(DRAFTS, uid)
    if old_raw is None:
        raise _not_found(uid, DRAFTS)
    kept, summary = _kept_from_old(old_raw, body_html)
    msg = _build_draft(
        app, to=to, subject=subject, body=body, body_html=body_html,
        cc=cc, bcc=bcc, reply_to=reply_to, **kept,
    )
    # Har utkastet ändrats sedan det lästes (i Proton) har det fått ett nytt
    # UID — IMAP-meddelanden ändras aldrig — och då avbryter replace_draft
    # med "Inget meddelande med UID …" i stället för att ersätta fel version.
    new_uid = await imap_drafts.replace_draft(app.imap, uid, msg.as_bytes(), msg["Message-ID"])
    return {
        **_draft_result(new_uid, msg),
        "replaced_uid": uid,
        "replaced_moved_to": imap_drafts.TRASH,
        **summary,
    }


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

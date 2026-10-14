import email
import email.policy
import re
from email.message import EmailMessage

from mcp.server.fastmcp import Context

from ..server import mcp
from ..email_parser import parse_email
from . import _get_app

# Svars- och vidarebefordringsprefix på olika språk: Re, SV/Svar-förkortningen
# (sv, da, no), AW (de), VS (fi), Antw (nl), Fw/Fwd, VB (sv "vidarebefordrat"),
# med valfri räknare som "Re[2]:" eller "RE (3):"
_PREFIX_RE = re.compile(
    r"^\s*(?:re|sv|aw|vs|antw|fwd?|vb)\s*(?:\[\d+\]|\(\d+\))?\s*:\s*",
    re.IGNORECASE,
)


def _parse_original(raw: bytes) -> EmailMessage:
    """Parsa originalet med den moderna policyn.

    Headers läses då skiftlägesokänsligt och avkodas korrekt, även råa
    UTF-8-headers (RFC 6532) och RFC 2047-kodade namn.
    """
    return email.message_from_bytes(raw, policy=email.policy.default)


def _header_text(msg: EmailMessage, name: str) -> str:
    """Avkodat headervärde på en enda rad (tomt om det saknas eller är trasigt)."""
    try:
        value = msg.get(name)
    except Exception:  # trasiga headers ska inte stoppa ett svar
        return ""
    # Kodade ord kan innehålla radbrytningar — slå ihop till en rad
    return " ".join(str(value or "").split())


def _base_subject(subject: str) -> str:
    """Ta bort alla inledande svars-/vidarebefordringsprefix."""
    while True:
        stripped = _PREFIX_RE.sub("", subject, count=1)
        if stripped == subject:
            return subject
        subject = stripped


@mcp.tool()
async def reply_to_email(
    ctx: Context,
    uid: str,
    body: str,
    mailbox: str = "INBOX",
    body_html: str | None = None,
) -> bool:
    """Svara på ett e-post. Sätter In-Reply-To, References och Re:-prefix automatiskt.

    Args:
        uid: UID för e-posten att svara på
        body: Svarstexten i klartext
        mailbox: Mappnamn (standard: INBOX)
        body_html: Valfri HTML-version av svarstexten
    """
    app = _get_app(ctx)
    raw = await app.imap.get_message(mailbox, uid)
    if raw is None:
        return False

    original = parse_email(raw, body_format="full")
    msg = _parse_original(raw)

    # Ett enda "Re: " oavsett hur många och vilka språks prefix som finns
    subject = f"Re: {_base_subject(_header_text(msg, 'Subject'))}"

    # Reply-to: svara till avsändaren
    reply_to_addr = original["from"]

    # Bygg In-Reply-To och References headers
    message_id = original["message_id"]
    additional_headers: dict[str, str] = {}
    if message_id:
        additional_headers["In-Reply-To"] = message_id
        # References: kedja vidare befintliga references + original message-id
        existing_refs = dict(original.get("headers", {})).get("References", "")
        if existing_refs:
            additional_headers["References"] = f"{existing_refs} {message_id}"
        else:
            additional_headers["References"] = message_id

    return await app.smtp.send_email(
        to=reply_to_addr,
        subject=subject,
        body=body,
        body_html=body_html,
        additional_headers=additional_headers,
    )


@mcp.tool()
async def forward_email(
    ctx: Context,
    uid: str,
    to: str | list[str],
    body: str = "",
    mailbox: str = "INBOX",
) -> bool:
    """Vidarebefordra ett e-post. Sätter Fwd:-prefix och citerar originalet.

    Args:
        uid: UID för e-posten att vidarebefordra
        to: Mottagaradress(er)
        body: Valfri text att lägga till ovanför det vidarebefordrade meddelandet
        mailbox: Mappnamn (standard: INBOX)
    """
    app = _get_app(ctx)
    raw = await app.imap.get_message(mailbox, uid)
    if raw is None:
        return False

    original = parse_email(raw, body_format="full")
    msg = _parse_original(raw)

    subject = f"Fwd: {_base_subject(_header_text(msg, 'Subject'))}"

    # Bygg vidarebefordrad body med citat
    orig_body = original.get("body_plain", "")
    forwarded = (
        f"{body}\n\n"
        f"---------- Forwarded message ----------\n"
        f"From: {original['from']}\n"
        f"Date: {original['date']}\n"
        f"Subject: {original['subject']}\n\n"
        f"{orig_body}"
    )

    return await app.smtp.send_email(
        to=to,
        subject=subject,
        body=forwarded,
    )

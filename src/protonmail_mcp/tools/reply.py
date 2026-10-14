import email
import email.policy
import re
from email.message import EmailMessage

from mcp.server.fastmcp import Context

from ..server import mcp
from ..email_parser import parse_email
from . import _get_app

# Svars- och vidarebefordringsprefix på olika språk: Re, SV (sv, da, no),
# AW (de), VS (fi), Antw (nl), Fw/Fwd, VB (sv "vidarebefordrat"), med valfri
# räknare som "Re[2]:" eller "RE (3):". Mönstret matchas från en given position
# och har inga intilliggande \s* — ämnet styrs av avsändaren, och överlappande
# kvantifierare gav kvadratisk tid på långa blankteckenserier.
_PREFIX_RE = re.compile(
    r"(?:re|sv|aw|vs|antw|fwd?|vb)(?:[ \t]*(?:\[\d+\]|\(\d+\)))?[ \t]*:",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s*")

_MSGID_RE = re.compile(r"<[^<>\s]+>")

# Hur stor en header i originalet får vara innan den parsas. Headerparsern i
# email.policy är superlinjär (ett ämne på 1 MB tog över 20 s), och originalet
# styrs av avsändaren. Normala headers är långt under en kilobyte.
_MAX_HEADER_CHARS = 50_000

# References trimmas som i vanliga e-postprogram: trådens rot och de senaste
_MAX_REFERENCES = 50


def _parse_original(raw: bytes) -> EmailMessage:
    """Parsa originalet med den moderna policyn.

    Headers läses då skiftlägesokänsligt och avkodas korrekt, även råa
    UTF-8-headers (RFC 6532) och RFC 2047-kodade namn.
    """
    return email.message_from_bytes(raw, policy=email.policy.default)


def _raw_values(msg: EmailMessage, name: str, limit: int | None = _MAX_HEADER_CHARS) -> list[str]:
    """Råa (oparsade) värden för en header, skiftlägesokänsligt."""
    key = name.lower()
    values = [str(v) for k, v in msg.raw_items() if k.lower() == key]
    if limit is not None:
        for value in values:
            if len(value) > limit:
                raise ValueError(
                    f"Originalets {name}-header är orimligt stor ({len(value)} tecken)"
                )
    return values


def _header_text(msg: EmailMessage, name: str) -> str:
    """Avkodat headervärde på en enda rad (tomt om det saknas)."""
    values = _raw_values(msg, name)
    if not values:
        return ""
    try:
        value = msg.policy.header_fetch_parse(name, values[0])
    except Exception:  # trasiga headers ska inte stoppa ett svar
        value = values[0]
    # Kodade ord kan innehålla radbrytningar — slå ihop till en rad
    return " ".join(str(value).split())


def _msg_ids(msg: EmailMessage, name: str) -> list[str]:
    """Alla <msg-id> i en header, i ordning och utan skräp mellan dem.

    Läses ur råvärdet: msg-id:n kodas aldrig, och regexen är linjär även för
    en mycket lång References-header.
    """
    ids: list[str] = []
    for value in _raw_values(msg, name, limit=None):
        ids.extend(_MSGID_RE.findall(value))
    return ids


def _threading_headers(msg: EmailMessage) -> dict[str, str]:
    """In-Reply-To och References för ett svar (RFC 5322 3.6.4)."""
    own_id = next(iter(_msg_ids(msg, "Message-ID")), "")
    if not own_id:
        return {}
    # Föräldrakedjan: References, annars In-Reply-To om den är ett enda id
    parents = _msg_ids(msg, "References")
    if not parents:
        in_reply_to = _msg_ids(msg, "In-Reply-To")
        if len(in_reply_to) == 1:
            parents = in_reply_to
    chain = list(dict.fromkeys(parents + [own_id]))
    if len(chain) > _MAX_REFERENCES:
        chain = chain[:1] + chain[-(_MAX_REFERENCES - 1):]
    return {"In-Reply-To": own_id, "References": " ".join(chain)}


def _base_subject(subject: str) -> str:
    """Ta bort alla inledande svars-/vidarebefordringsprefix (linjär tid)."""
    pos = 0
    while True:
        pos = _WS_RE.match(subject, pos).end()
        match = _PREFIX_RE.match(subject, pos)
        if match is None:
            return subject[pos:]
        pos = match.end()


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

    additional_headers = _threading_headers(msg)

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

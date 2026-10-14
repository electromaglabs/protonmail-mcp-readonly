import email
import email.policy
import html
import re
from collections.abc import Sequence
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime

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
_ANGLE_ADDR_RE = re.compile(r"<([^<>\s@]+@[^<>\s@]+)>")

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


def _decode_8bit(value: str) -> str:
    """Gör råa 8-bitarsheaders (RFC 6532) till text före parsningen.

    Parsern lämnar dem som surrogat-escapes, och i adressheaders hamnar de
    då oavkodade i display-namnet.
    """
    if value.isascii():
        return value
    data = value.encode("utf-8", "surrogateescape")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _raw_values(msg: EmailMessage, name: str, limit: int | None = _MAX_HEADER_CHARS) -> list[str]:
    """Råa (oparsade) värden för en header, skiftlägesokänsligt.

    Gränsen gäller summan av alla förekomster — annars kan avsändaren dela
    upp en enorm header på många rader med samma namn.
    """
    key = name.lower()
    values = [str(v) for k, v in msg.raw_items() if k.lower() == key]
    total = sum(len(v) for v in values)
    if limit is not None and total > limit:
        raise ValueError(
            f"Originalets {name}-header är orimligt stor ({total} tecken)"
        )
    return [_decode_8bit(v) for v in values]


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
        # Ett msg-id är ASCII; ett id med 8-bitarstecken kan inte skickas
        # vidare i en header och hoppas över
        ids.extend(i for i in _MSGID_RE.findall(value) if i.isascii())
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


def _addresses(msg: EmailMessage, name: str) -> list[tuple[str, str]]:
    """(namn, adress) för alla adresser i en adressheader.

    Läses ur den råa headern så att namn och adress hålls isär: ett avkodat
    namn som "Svensson, Åsa" får aldrig skickas vidare som adresssträng, där
    kommat skulle göra det till två (ogiltiga) adresser.
    """
    pairs: list[tuple[str, str]] = []
    for raw in _raw_values(msg, name):
        try:
            header = msg.policy.header_fetch_parse(name, raw)
            found = [(a.display_name, a.addr_spec) for a in header.addresses]
        except Exception:
            # Trasig header (t.ex. ett kodat namn med radbrytning): ta bara
            # adresserna inom <>, utan namn, och annars en enkel tolkning
            found = [("", addr) for addr in _ANGLE_ADDR_RE.findall(raw)]
            found = found or getaddresses([raw])
        pairs.extend(
            (" ".join(display.split()), addr) for display, addr in found if "@" in addr
        )
    return pairs


def _format_address(display: str, addr: str) -> str:
    """Adresssträng med namnet citerat vid behov ("Doe, John" <j@x.com>)."""
    try:
        return str(Address(display_name=display, addr_spec=addr))
    except Exception:  # adressen går inte att uttrycka med namn — skicka den naken
        return addr


def _own_address(app) -> str:
    """Det egna kontots adress i gemener ("" om den inte går att avgöra)."""
    addr = getattr(app.smtp, "account_address", "")
    return addr.lower() if isinstance(addr, str) else ""


def _reply_recipients(
    msg: EmailMessage,
    own: str,
    reply_all: bool,
    extra_cc: list[str],
) -> tuple[list[str], list[str]]:
    """(To, Cc) för ett svar, utan det egna kontot och utan dubbletter."""
    senders = _addresses(msg, "From")
    original_to = _addresses(msg, "To")
    original_cc = _addresses(msg, "Cc")

    if own and senders and all(addr.lower() == own for _, addr in senders):
        # Svar på ett eget skickat mejl: fortsätt till samma mottagare
        to_pairs = original_to
    else:
        to_pairs = _addresses(msg, "Reply-To") or senders
        if reply_all:
            to_pairs = to_pairs + original_to
    cc_pairs = original_cc if reply_all else []
    cc_pairs = cc_pairs + [("", addr) for addr in extra_cc]

    seen = {own} if own else set()

    def take(pairs: list[tuple[str, str]]) -> list[str]:
        result = []
        for display, addr in pairs:
            key = addr.lower()
            if key not in seen:
                seen.add(key)
                result.append(_format_address(display, addr) if display else addr)
        return result

    to_list = take(to_pairs)
    cc_list = take(cc_pairs)
    if not to_list:
        # T.ex. ett eget mejl som bara hade Cc: låt kopian bli mottagare
        to_list, cc_list = cc_list, []
    if not to_list:
        raise ValueError(
            "Hittar ingen mottagare att svara till: originalet har inga andra "
            "adresser än ditt eget konto"
        )
    return to_list, cc_list


def _as_list(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _attribution(msg: EmailMessage) -> str:
    """"Den 2026-10-12 09:30 skrev Anna Ek:" (eller kortare om datum saknas)."""
    senders = _addresses(msg, "From")
    name = (senders[0][0] or senders[0][1]) if senders else "Avsändaren"
    date = _header_text(msg, "Date")
    try:
        date = parsedate_to_datetime(date).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, IndexError, OverflowError):
        pass  # okänt datumformat — visa det som det står
    return f"Den {date} skrev {name}:" if date else f"{name} skrev:"


def _original_text(raw: bytes) -> str:
    """Originalets brödtext som ren text (HTML-brev görs om till text)."""
    text = parse_email(raw, body_format="text", max_length=None)["body_plain"]
    return text.replace("\r\n", "\n").rstrip()


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))


def _insert_before_body_end(document: str, fragment: str) -> str:
    """Lägg in fragmentet före </body> om dokumentet har en, annars sist."""
    end = document.lower().rfind("</body>")
    if end < 0:
        return f"{document}\n{fragment}"
    return f"{document[:end]}{fragment}\n{document[end:]}"


@mcp.tool()
async def reply_to_email(
    ctx: Context,
    uid: str,
    body: str,
    mailbox: str = "INBOX",
    body_html: str | None = None,
    reply_all: bool = False,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    quote_original: bool = True,
) -> bool:
    """Svara på ett e-post. Sätter In-Reply-To, References och Re:-prefix automatiskt.

    Svaret går till originalets Reply-To om den finns, annars till From. Är
    originalet ett mejl du själv skickat går svaret till dess mottagare.
    Originalet citeras under svaret ("Den <datum> skrev <namn>:" och "> "-rader).

    Args:
        uid: UID för e-posten att svara på
        body: Svarstexten i klartext
        mailbox: Mappnamn (standard: INBOX)
        body_html: Valfri HTML-version av svarstexten
        reply_all: Svara alla — ta även med originalets To och Cc (utom ditt eget konto)
        cc: Ytterligare kopia-adress(er)
        bcc: Hemlig kopia-adress(er)
        quote_original: Citera originalet under svaret (standard: True)

    Returns:
        True om svaret skickades. Vägrar servern några av mottagarna kastas
        ett fel som anger vilka — skicka då inte om till alla.
    """
    app = _get_app(ctx)
    raw = await app.imap.get_message(mailbox, uid)
    if raw is None:
        return False

    msg = _parse_original(raw)

    # Ett enda "Re: " oavsett hur många och vilka språks prefix som finns
    subject = f"Re: {_base_subject(_header_text(msg, 'Subject'))}"

    to_list, cc_list = _reply_recipients(
        msg, _own_address(app), reply_all, _as_list(cc)
    )

    if quote_original:
        attribution = _attribution(msg)
        original_text = _original_text(raw)
        body = f"{body}\n\n{attribution}\n{_quote(original_text)}\n"
        if body_html:
            quoted_html = html.escape(original_text).replace("\n", "<br>\n")
            body_html = _insert_before_body_end(
                body_html,
                f"<div>{html.escape(attribution)}</div>\n"
                '<blockquote type="cite" style="margin:0 0 0 .8ex;'
                'border-left:1px solid #ccc;padding-left:1ex">'
                f"{quoted_html}</blockquote>",
            )

    return await app.smtp.send_email(
        to=to_list,
        subject=subject,
        body=body,
        body_html=body_html,
        cc=cc_list or None,
        bcc=bcc,
        additional_headers=_threading_headers(msg),
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

import email
import email.policy
import html
import re
from collections.abc import Sequence
from email.headerregistry import Address
from email.message import EmailMessage, Message
from email.utils import getaddresses, parsedate_to_datetime

from mcp.server.fastmcp import Context

from ..server import mcp
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
# [^<>]* i stället för [^>]*: annars blir sökningen kvadratisk på "<body<body…"
_BODY_OPEN_RE = re.compile(r"<body\b[^<>]*>", re.IGNORECASE)
_CID_REF_RE = re.compile(r"cid:([^\s\"'<>()]+)", re.IGNORECASE)
# En tagg börjar med bokstav, / ! eller ? ("1 < 2" är text). [^<>]* gör att
# varje försök stannar vid nästa "<", så genomsökningen blir linjär.
_TAG_RE = re.compile(r"<[/!?a-zA-Z][^<>]*>")
_TAG_NAME_RE = re.compile(r"</?([a-zA-Z0-9]+)")
_BLOCK_TAGS = frozenset(
    "br p div tr li h1 h2 h3 h4 h5 h6 table ul ol blockquote title hr".split()
)

# Hur stor en header i originalet får vara innan den parsas. Headerparsern i
# email.policy är superlinjär (ett ämne på 1 MB tog över 20 s), och originalet
# styrs av avsändaren. Normala headers är långt under en kilobyte.
_MAX_HEADER_CHARS = 50_000

# References trimmas som i vanliga e-postprogram: trådens rot och de senaste
_MAX_REFERENCES = 50


# MIME-headers som parsas för varje del (typ, disposition, kodning) är normalt
# under ett par hundra tecken; summan av alla headers i alla delar begränsas
# också, eftersom varje del har egna headers som avsändaren styr.
_MAX_MIME_HEADER_CHARS = 10_000
_MAX_TOTAL_HEADER_CHARS = 1_000_000
# Varje del parsas (Content-Type) med email.policy: 20 000 små delar tog
# flera sekunder. Vanliga mejl har högst några tiotal delar.
_MAX_MIME_PARTS = 1_000
_MIME_HEADERS = frozenset(
    ("content-type", "content-disposition", "content-transfer-encoding")
)


def _parse_original(raw: bytes) -> EmailMessage:
    """Parsa originalet med den moderna policyn.

    Headers läses då skiftlägesokänsligt och avkodas korrekt, även råa
    UTF-8-headers (RFC 6532) och RFC 2047-kodade namn.
    """
    # Storlekskontrollen görs på en compat32-parsning, som är billig: redan
    # parsningen med email.policy.default läser varje dels Content-Type med
    # den superlinjära headerparsern (60 delar à 45 000 tecken: 0,7–1,2 s).
    _check_header_sizes(email.message_from_bytes(raw, policy=email.policy.compat32))
    return email.message_from_bytes(raw, policy=email.policy.default)


def _check_header_sizes(msg: Message) -> None:
    """Avvisa orimligt stora headers innan något av dem parsas (linjär tid)."""
    total = 0
    parts = 0
    stack = [msg]
    while stack:
        part = stack.pop()
        parts += 1
        if parts > _MAX_MIME_PARTS:
            raise ValueError(
                f"Originalet har orimligt många MIME-delar (över {_MAX_MIME_PARTS})"
            )
        for name, value in part.raw_items():
            size = len(str(value))
            total += size
            if name.lower() in _MIME_HEADERS and size > _MAX_MIME_HEADER_CHARS:
                raise ValueError(
                    f"Originalet har en orimligt stor {name}-header ({size} tecken)"
                )
        if total > _MAX_TOTAL_HEADER_CHARS:
            raise ValueError(
                f"Originalets headers är orimligt stora ({total} tecken totalt)"
            )
        # get_payload() i stället för iter_parts(): det senare parsar Content-Type
        payload = part.get_payload() if part.is_multipart() else None
        if isinstance(payload, list):
            stack.extend(payload)


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


def _part_text(part: EmailMessage | None) -> str:
    """Textinnehållet i en MIME-del, tålig mot okända teckenkodningar."""
    if part is None:
        return ""
    try:
        return part.get_content()
    except (LookupError, UnicodeError, KeyError, AssertionError):
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="replace")


def _html_to_text(markup: str) -> str:
    """Enkel textversion av HTML i linjär tid.

    Taggar tas bort, block (p, div, br …) blir radbrytningar, script och
    style hoppas över och entiteter avkodas. Görs här i stället för med
    email_parser._strip_html, vars <[^>]+> är kvadratisk på t.ex.
    "<body<body…" — och HTML:en styrs av avsändaren.
    """
    pieces: list[str] = []
    pos = 0
    skip = ""
    for tag in _TAG_RE.finditer(markup):
        if not skip:
            pieces.append(markup[pos:tag.start()])
        pos = tag.end()
        text = tag.group()
        named = _TAG_NAME_RE.match(text)
        name = named.group(1).lower() if named else ""
        closing = text.startswith("</")
        if skip:
            if closing and name == skip:
                skip = ""
        elif name in ("script", "style") and not closing:
            skip = name
        elif name in _BLOCK_TAGS:
            pieces.append("\n")
    if not skip:
        pieces.append(markup[pos:])
    lines = (" ".join(line.split()) for line in html.unescape("".join(pieces)).splitlines())
    return "\n".join(line for line in lines if line)


def _original_text(msg: EmailMessage) -> str:
    """Originalets brödtext som ren text (HTML-brev görs om till text)."""
    text = _part_text(msg.get_body(("plain",)))
    if not text.strip():
        text = _html_to_text(_part_text(msg.get_body(("html",))))
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
        original_text = _original_text(msg)
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


def _content_id(part: EmailMessage) -> str:
    raw = next((str(v) for k, v in part.raw_items() if k.lower() == "content-id"), "")
    return raw.strip().strip("<>").strip()


def _forward_parts(
    msg: EmailMessage, body_parts: list[EmailMessage], html: str
) -> tuple[list[EmailMessage], list[EmailMessage]]:
    """(inline-delar, bilagor) ur originalet, utom brödtextdelarna.

    Alla lövdelar följer med oförändrade; ett bifogat mejl (message/rfc822)
    följer med som helhet. Delar som HTML-versionen pekar på med cid: blir
    inline-delar, så att bilderna fortsätter att visas.
    """
    referenced = {cid.lower() for cid in _CID_REF_RE.findall(html)}
    inline: list[EmailMessage] = []
    attached: list[EmailMessage] = []
    stack = [msg]
    while stack:  # iterativt — djupt nästlade multipart ska inte ge RecursionError
        part = stack.pop()
        if part.get_content_maintype() == "multipart":
            stack.extend(reversed(list(part.iter_parts())))
        elif not any(part is body for body in body_parts):
            cid = _content_id(part)
            (inline if cid and cid.lower() in referenced else attached).append(part)
    return inline, attached


def _escape_lines(text: str) -> str:
    return html.escape(text).replace("\n", "<br>\n")


@mcp.tool()
async def forward_email(
    ctx: Context,
    uid: str,
    to: str | list[str],
    body: str = "",
    mailbox: str = "INBOX",
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
) -> bool:
    """Vidarebefordra ett e-post med originalets text, HTML-version och bilagor.

    Sätter Fwd:-prefix. Originalet följer med inline under ett rubrikblock
    ("Forwarded message"), både som text och — om originalet har en sådan —
    som HTML. Alla bilagor, bifogade mejl och inbäddade bilder följer med.

    Args:
        uid: UID för e-posten att vidarebefordra
        to: Mottagaradress(er)
        body: Valfri text att lägga till ovanför det vidarebefordrade meddelandet
        mailbox: Mappnamn (standard: INBOX)
        cc: Kopia-adress(er)
        bcc: Hemlig kopia-adress(er)

    Returns:
        True om mejlet skickades. Vägrar servern några av mottagarna kastas
        ett fel som anger vilka — skicka då inte om till alla.
    """
    app = _get_app(ctx)
    raw = await app.imap.get_message(mailbox, uid)
    if raw is None:
        return False

    msg = _parse_original(raw)
    subject = f"Fwd: {_base_subject(_header_text(msg, 'Subject'))}"

    header_lines = ["---------- Forwarded message ----------"]
    for name in ("From", "Date", "Subject", "To", "Cc"):
        value = _header_text(msg, name)
        if value:
            header_lines.append(f"{name}: {value}")

    plain_part = msg.get_body(("plain",))
    html_part = msg.get_body(("html",))
    orig_html = _part_text(html_part)
    # HTML-brev får en textversion, så att även textdelen har innehållet
    orig_text = _original_text(msg)

    intro = f"{body}\n\n" if body else ""
    forwarded = f"{intro}" + "\n".join(header_lines) + f"\n\n{orig_text}\n"

    forwarded_html = None
    if orig_html:
        prefix = (f"<div>{_escape_lines(body)}</div><br>\n" if body else "") + (
            f"<div>{_escape_lines(chr(10).join(header_lines))}</div><br>\n"
        )
        opening = _BODY_OPEN_RE.search(orig_html)
        cut = opening.end() if opening else 0
        forwarded_html = orig_html[:cut] + prefix + orig_html[cut:]

    body_parts = [p for p in (plain_part, html_part) if p is not None]
    inline, attached = _forward_parts(msg, body_parts, orig_html)

    return await app.smtp.send_email(
        to=to,
        subject=subject,
        body=forwarded,
        body_html=forwarded_html,
        cc=cc,
        bcc=bcc,
        attachments=attached or None,
        inline_parts=inline or None,
    )

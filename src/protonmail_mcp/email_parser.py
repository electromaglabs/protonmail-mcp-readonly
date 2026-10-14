import binascii
import codecs
import email
import email.header
import email.quoprimime
import email.utils
import re
from email.message import Message
from typing import Any

from .html_text import html_to_text

# Etiketter som är vanliga i post men saknas i Python eller oftast är fel
_CHARSET_ALIASES = {
    "us-ascii": "utf-8",  # 8-bitars data märkt us-ascii är nästan alltid utf-8
    "ascii": "utf-8",
    "gb2312": "gb18030",  # gb2312 ⊂ gbk ⊂ gb18030; felmärkt GBK är vanligt
    "gbk": "gb18030",
    "x-gbk": "gb18030",
    "x-mac-roman": "mac_roman",
    "macintosh": "mac_roman",
    "ks_c_5601-1987": "cp949",
}

# Codecs som Python räknar som text men som omtolkar innehållet i stället för
# att avkoda en teckenkodning (unicode_escape tolkar \x41, punycode/idna är
# domännamnsformat)
_REJECTED_CODECS = {"unicode-escape", "raw-unicode-escape", "punycode", "idna", "undefined"}
_BOM_CODECS = {"utf-16", "utf-32"}


def _lookup_charset(charset: str | None) -> str | None:
    """Returnera ett användbart codec-namn för en MIME-charset, eller None."""
    if not charset:
        return None
    name = str(charset).strip().strip('"').lower()
    name = name.split("*", 1)[0]  # RFC 2231 §5: språktagg, "utf-8*sv"
    name = _CHARSET_ALIASES.get(name, name)
    try:
        info = codecs.lookup(name)
    except (LookupError, ValueError, TypeError):
        return None
    if not getattr(info, "_is_text_encoding", True) or info.name in _REJECTED_CODECS:
        return None
    return info.name


def _decode_bytes(data: bytes, charset: str | None) -> str:
    """Avkoda bytes med deklarerad charset utan att någonsin kasta.

    Ordning: deklarerad charset (strikt) → utf-8 (strikt) → cp1252 (strikt) →
    deklarerad charset med ersättningstecken → latin-1, som alltid lyckas.
    """
    codec = _lookup_charset(charset)
    if codec in _BOM_CODECS and not data.startswith(
        (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE, codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)
    ):
        codec = None  # utan BOM gissar Python byteordning och ger mojibake
    for candidate in (codec, "utf-8", "cp1252"):
        if candidate is None:
            continue
        try:
            return data.decode(candidate)
        except (UnicodeError, LookupError, ValueError):
            continue
    if codec is not None:
        try:
            return data.decode(codec, errors="replace")
        except (UnicodeError, LookupError, ValueError):
            pass
    return data.decode("latin-1")


# RFC 2047 encoded-word. encoded-text får inte innehålla '?' (§4), så texten
# slutar vid första '?' — annars letar varje oavslutat "=?" efter "?=" ända
# till slutet av rubriken och avkodningen blir kvadratisk (S1). Ett okodat '?'
# sist i ett Q-ord ("du??=") tillåts ändå, som i email.header.
_ENCODED_WORD_RE = re.compile(
    r"=\?(?P<charset>[^?]*)\?(?P<encoding>[qQbB])\?(?P<text>[^?]*\??)\?="
)


def _decode_encoded_word(encoding: str, text: str) -> bytes | None:
    try:
        if encoding.lower() == "q":
            return email.quoprimime.header_decode(text).encode("latin-1")
        padded = text + "=" * (-len(text) % 4)
        return binascii.a2b_base64(padded.encode("ascii"))
    except (binascii.Error, UnicodeError, ValueError):
        return None


def _decode_rfc2047(text: str) -> str:
    """Avkoda RFC 2047-ord. Blanktecken mellan två kodade ord tas bort, och
    intilliggande ord med samma charset avkodas tillsammans så att ett tecken
    som delats mellan två ord blir helt."""
    out: list[str] = []
    pending = b""
    pending_charset = ""
    prev_encoded = False
    pos = 0

    def flush() -> None:
        nonlocal pending
        if pending:
            out.append(_decode_bytes(pending, pending_charset))
        pending = b""

    for m in _ENCODED_WORD_RE.finditer(text):
        between = text[pos : m.start()]
        pos = m.end()
        decoded = _decode_encoded_word(m.group("encoding"), m.group("text"))
        if decoded is None:  # trasigt kodat ord — behåll det som text
            flush()
            out.append(between + m.group(0))
            prev_encoded = False
            continue
        charset = m.group("charset")
        if not (prev_encoded and not between.strip()):
            flush()
            out.append(between)
        elif charset.lower() != pending_charset.lower():
            flush()
        if not pending:
            pending_charset = charset
        pending += decoded
        prev_encoded = True
    flush()
    out.append(text[pos:])
    return "".join(out)


def _header_to_text(value) -> str:
    """Gör om ett rått rubrikvärde till str utan att tappa 8-bitars tecken.

    Både compat32-parsern och IMAP-metadata lämnar rå UTF-8 (RFC 6532) som
    surrogateescape-str eller som Header-objekt med unknown-8bit; str() på
    dem ger U+FFFD. Bytesen avkodas i stället som utf-8 → cp1252 → latin-1.
    """
    if isinstance(value, email.header.Header):
        try:
            return "".join(
                part if isinstance(part, str)
                else _decode_bytes(part, None if charset in (None, "unknown-8bit") else charset)
                for part, charset in email.header.decode_header(value)
            )
        except Exception:
            return str(value)
    text = str(value)
    if any("\udc80" <= ch <= "\udcff" for ch in text):
        text = _decode_bytes(text.encode("utf-8", "surrogateescape"), None)
    return text


def decode_header_value(value) -> str:
    if not value:
        return ""
    value = _header_to_text(value)
    # Avkodade ord kan dölja radbrytningar (CR/LF men även \v, \f, \x1c-\x1e,
    # \x85, U+2028/2029 som str.splitlines() räknar) — slå ihop till en rad så
    # värdet inte kan injicera headers
    text = _decode_rfc2047(value)
    lines = text.splitlines()
    if lines == [text] or not lines:
        return text
    # Linjär tid (ingen regex med överlappande \s*, som gav ReDoS); trimma
    # varje rad så att en vikt rad "a\r\n b" blir "a b" och inte "a  b"
    return " ".join(stripped for line in lines if (stripped := line.strip()))


# Tecken som kräver citering av visningsnamnet (RFC 5322 specials, som formataddr)
_ADDR_SPECIALS_RE = re.compile(r'[][\\()<>@,:;".]')
_ADDR_ESCAPES_RE = re.compile(r'[\\"]')


def parse_addresses(header_value) -> list[tuple[str, str]]:
    """Parsa en adressrubrik till (namn, adress)-par med avkodade namn.

    Adresslistan delas upp FÖRE RFC 2047-avkodningen, så att ett kodat
    kommatecken eller "<…>" i namnet inte kan skapa nya adresser. Bara
    namnet avkodas: kodade ord är inte tillåtna i adressdelen (RFC 2047 §5),
    och att avkoda dem där skulle låta avsändaren tillverka en annan adress.
    """
    if not header_value:
        return []
    text = _header_to_text(header_value)
    pairs = []
    for name, addr in email.utils.getaddresses([text]):
        name, addr = decode_header_value(name), "".join(addr.split())
        if addr:  # ett namn utan adress går inte att skicka till
            pairs.append((name, addr))
    return pairs


def _parses_to(formatted: str, addr: str) -> bool:
    """Ger strängen exakt en adress, och är det addr?"""
    try:
        found = [a for _, a in email.utils.getaddresses([formatted]) if a]
    except Exception:
        return False
    return found == [addr]


def format_address(name: str, addr: str) -> str:
    """Som email.utils.formataddr men utan att RFC 2047-koda icke-ASCII-namn:
    namn med specialtecken citeras så att strängen kan parsas tillbaka.

    Ingen tolkningsskillnad: resultatet parsas alltid till exakt addr (som
    reply_to_email skickar till). Går det inte med namnet blir det bara
    adressen, och går inte ens den att parsa tillbaka blir det "".
    """
    candidates = [addr]
    if name:
        if _ADDR_SPECIALS_RE.search(name):
            name = '"%s"' % _ADDR_ESCAPES_RE.sub(r"\\\g<0>", name)
        candidates.insert(0, f"{name} <{addr}>")
    for candidate in candidates:
        if addr and _parses_to(candidate, addr):
            return candidate
    return ""


def extract_addresses(header_value: str | None) -> list[str]:
    formatted = (format_address(name, addr) for name, addr in parse_addresses(header_value))
    return [a for a in formatted if a]


def _safe_decode(payload: bytes, charset: str | None) -> str:
    """Dekodar payload med angiven charset utan att kasta (se _decode_bytes)."""
    return _decode_bytes(payload, charset)


_MAX_MIME_DEPTH = 100


def _filename(part: Message) -> str:
    try:
        return decode_header_value(part.get_filename())
    except Exception:
        return ""


def _disposition(part: Message) -> str | None:
    try:
        return part.get_content_disposition()  # gemener: "attachment"/"inline"
    except Exception:
        return None


def _attachment(part: Message, filename: str) -> dict[str, Any]:
    if part.is_multipart():
        # message/rfc822: get_payload(decode=True) är None för multipart
        try:
            size = sum(len(p.as_bytes()) for p in part.get_payload() if isinstance(p, Message))
        except Exception:
            size = 0
    else:
        size = len(part.get_payload(decode=True) or b"")
    return {"filename": filename, "content_type": part.get_content_type(), "size": size}


def _text_of(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    try:
        charset = part.get_content_charset()
    except Exception:
        charset = None
    return _safe_decode(payload, charset)


def _collect(part: Message, out: dict[str, list], depth: int = 0) -> None:
    """Samla brödtext och bilagor för ett meddelande.

    Går inte ner i message/* (vidarebefordrade mejl är bilagor, inte en del
    av ytterbrevet). I multipart/alternative tas en variant per typ; i övriga
    multipart (mixed, related, signed …) slås alla inline-textdelar ihop.
    """
    if depth > _MAX_MIME_DEPTH:
        return
    ctype = part.get_content_type()
    maintype = part.get_content_maintype()

    if maintype == "message" and part.is_multipart():
        out["attachments"].append(_attachment(part, _filename(part)))
        return

    if part.is_multipart():
        children = [c for c in part.get_payload() if isinstance(c, Message)]
        if part.get_content_subtype() != "alternative":
            for child in children:
                _collect(child, out, depth + 1)
            return
        for child in children:
            sub: dict[str, list] = {"plain": [], "html": [], "attachments": []}
            _collect(child, sub, depth + 1)
            for kind in ("plain", "html"):
                if not out[kind] and any(sub[kind]):
                    out[kind].extend(sub[kind])
            out["attachments"].extend(sub["attachments"])
        return

    disposition = _disposition(part)
    filename = _filename(part)
    is_text_body = (
        ctype in ("text/plain", "text/html") or maintype == "multipart"  # trasig multipart utan boundary
    ) and disposition != "attachment" and (not filename or disposition == "inline")
    if is_text_body:
        if text := _text_of(part):
            out["html" if ctype == "text/html" else "plain"].append(text)
    elif disposition == "attachment" or filename:
        out["attachments"].append(_attachment(part, filename))
    elif disposition == "inline" or part.get("Content-ID"):
        pass  # inbäddad resurs utan filnamn, t.ex. cid-logga i multipart/related
    elif maintype == "text" and ctype != "text/calendar":
        pass  # annan textvariant i alternative, t.ex. text/x-amp-html
    else:
        out["attachments"].append(_attachment(part, filename))


def _parts(msg: Message) -> dict[str, list]:
    out: dict[str, list] = {"plain": [], "html": [], "attachments": []}
    _collect(msg, out)
    return out


def get_body(msg: Message) -> dict[str, str]:
    parts = _parts(msg)
    return {"plain": "\n".join(parts["plain"]), "html": "\n".join(parts["html"])}


def get_attachments(msg: Message) -> list[dict[str, Any]]:
    return _parts(msg)["attachments"]


def _strip_html(html: str) -> str:
    """Gör om HTML till läsbar text (se html_text.html_to_text)."""
    return html_to_text(html)


def _strip_quotes_and_signature(text: str) -> str:
    """Ta bort citat (rader som börjar med >) och signaturblock (efter '-- ')."""
    lines = text.splitlines()
    result = []
    for line in lines:
        # Signaturavgränsaren är exakt "-- " (RFC 3676 §4.3); ett ensamt "--"
        # är ofta en avskiljare mitt i texten och får inte kapa resten
        if line == "-- ":
            break
        # Hoppa över citerade rader
        if line.startswith(">"):
            continue
        result.append(line)
    return "\n".join(result)


def _truncate(text: str, max_length: int | None) -> str:
    """Trunkera text till max_length tecken med hint om kvarvarande."""
    if max_length is None or len(text) <= max_length:
        return text
    remaining = len(text) - max_length
    return text[:max_length] + f"\n[...{remaining} characters remaining]"


_BODY_FORMATS = ("text", "full", "stripped")

# Vedertagen stavning för rubriker som anropare slår upp i headers-dicten
_CANONICAL_HEADERS = {
    name.lower(): name
    for name in (
        "From", "To", "Cc", "Bcc", "Reply-To", "Sender", "Subject", "Date",
        "Message-ID", "In-Reply-To", "References", "Return-Path", "Received",
        "MIME-Version", "Content-Type", "Content-Transfer-Encoding",
        "Content-Disposition", "Content-ID", "List-Unsubscribe", "List-Id",
    )
}


def _headers_dict(msg: Message) -> dict[str, str]:
    """Rubriker som str. Nycklar är skiftlägesokänsliga i e-post (RFC 5322):
    välkända rubriker får vedertagen stavning, övriga stavningen från första
    förekomsten, och vid dubbletter gäller första förekomsten — samma värde
    som message_id/references m.fl. bygger på."""
    headers: dict[str, str] = {}
    seen: set[str] = set()
    for key, value in msg.raw_items():
        lower = key.lower()
        if lower in seen:
            continue
        seen.add(lower)
        headers[_CANONICAL_HEADERS.get(lower, key)] = decode_header_value(value)
    return headers


def _raw_header(msg: Message, name: str) -> str | None:
    """Första förekomsten av en rubrik, rå (före compat32:s Header-omvandling)."""
    wanted = name.lower()
    for key, value in msg.raw_items():
        if key.lower() == wanted:
            return value
    return None


def parse_email(
    raw: bytes,
    body_format: str = "text",
    max_length: int | None = 500,
) -> dict[str, Any]:
    if body_format not in _BODY_FORMATS:
        raise ValueError(
            f"Okänt body_format {body_format!r} — giltiga värden: {', '.join(_BODY_FORMATS)}"
        )
    if max_length is not None and max_length < 0:
        raise ValueError(f"max_length måste vara 0 eller större (eller None), fick {max_length}")
    msg = email.message_from_bytes(raw)
    parts = _parts(msg)

    body_plain = "\n".join(parts["plain"])
    body_html = "\n".join(parts["html"])

    if body_format == "full":
        # Returnera råa body utan trunkering
        pass
    elif body_format == "text":
        # Saknas text (eller är den bara blanktecken, vanligt i utskick): använd HTML
        if not body_plain.strip() and body_html:
            body_plain = _strip_html(body_html)
        body_plain = _truncate(body_plain, max_length)
    elif body_format == "stripped":
        if not body_plain.strip() and body_html:
            body_plain = _strip_html(body_html)
        body_plain = _strip_quotes_and_signature(body_plain)
        body_plain = _truncate(body_plain, max_length)

    if body_format != "full":
        # HTML är ofta 100+ KB (nyhetsbrev) — samma gräns som body_plain, så att
        # förvalda parametrar inte spräcker klientens kontext. Hela HTML:en
        # finns i "full" eller med max_length=None.
        body_html = _truncate(body_html, max_length)

    addresses = {
        key: parse_addresses(_raw_header(msg, name))
        for key, name in (
            ("from", "From"), ("to", "To"), ("cc", "Cc"), ("bcc", "Bcc"), ("reply_to", "Reply-To")
        )
    }
    formatted = {
        key: [f for f in (format_address(n, a) for n, a in pairs) if f]
        for key, pairs in addresses.items()
    }
    # Utan parsbar adress (bara ett namn, trasig rubrik): visa den avkodade texten
    from_ = ", ".join(formatted["from"])
    if not any("@" in addr for _, addr in addresses["from"]):
        # Bara ett namn: visa avkodad text — men aldrig om den avkodade texten
        # i sig kan tolkas som adresser (kodat "a@x.se, evil@y.se")
        decoded = decode_header_value(_raw_header(msg, "From"))
        if not any("@" in a for _, a in email.utils.getaddresses([decoded])):
            from_ = decoded

    return {
        "message_id": decode_header_value(_raw_header(msg, "Message-ID")),
        "subject": decode_header_value(_raw_header(msg, "Subject")),
        "from": from_,
        "to": formatted["to"],
        "cc": formatted["cc"],
        "bcc": formatted["bcc"],
        "reply_to": formatted["reply_to"],
        # (namn, adress)-par, för anropare som vill ha adressen utan att parsa om
        "addresses": {key: [[n, a] for n, a in pairs] for key, pairs in addresses.items()},
        "date": decode_header_value(_raw_header(msg, "Date")),
        "body_plain": body_plain,
        "body_html": body_html,
        "attachments": parts["attachments"],
        "in_reply_to": decode_header_value(_raw_header(msg, "In-Reply-To")),
        "references": decode_header_value(_raw_header(msg, "References")),
        "headers": _headers_dict(msg),
    }


def parse_envelope(envelope_data: str) -> dict[str, str]:
    """Parsar en IMAP ENVELOPE-sträng till ett enkelt dict med metadata."""
    # Returnerar rådata — full parsning görs av aioimaplib
    return {"raw": envelope_data}

import binascii
import codecs
import email
import email.header
import email.quoprimime
import email.utils
import re
from email.message import Message
from typing import Any

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


# RFC 2047 encoded-word, lika tillåtande som email.header.ecre
_ENCODED_WORD_RE = re.compile(
    r"=\?(?P<charset>[^?]*?)\?(?P<encoding>[qQbB])\?(?P<text>.*?)\?=", re.DOTALL
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


def decode_header_value(value) -> str:
    if not value:
        return ""
    value = str(value)
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


def extract_addresses(header_value: str | None) -> list[str]:
    if not header_value:
        return []
    addresses = email.utils.getaddresses([header_value])
    return [f"{name} <{addr}>" if name else addr for name, addr in addresses]


def _safe_decode(payload: bytes, charset: str | None) -> str:
    """Dekodar payload med angiven charset utan att kasta (se _decode_bytes)."""
    return _decode_bytes(payload, charset)


def get_body(msg: Message) -> dict[str, str]:
    plain = ""
    html = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition:
                continue
            charset = part.get_content_charset() or "utf-8"
            if content_type == "text/plain" and not plain:
                payload = part.get_payload(decode=True)
                if payload:
                    plain = _safe_decode(payload, charset)
            elif content_type == "text/html" and not html:
                payload = part.get_payload(decode=True)
                if payload:
                    html = _safe_decode(payload, charset)
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            content_type = msg.get_content_type()
            if content_type == "text/html":
                html = _safe_decode(payload, charset)
            else:
                plain = _safe_decode(payload, charset)

    return {"plain": plain, "html": html}


def get_attachments(msg: Message) -> list[dict[str, Any]]:
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition:
                filename = decode_header_value(part.get_filename())
                attachments.append(
                    {
                        "filename": filename,
                        "content_type": part.get_content_type(),
                        "size": len(part.get_payload(decode=True) or b""),
                    }
                )
    return attachments


def _strip_html(html: str) -> str:
    """Ta bort HTML-taggar och returnera ren text."""
    return re.sub(r"<[^>]+>", "", html).strip()


def _strip_quotes_and_signature(text: str) -> str:
    """Ta bort citat (rader som börjar med >) och signaturblock (efter '-- ')."""
    lines = text.splitlines()
    result = []
    for line in lines:
        # Signaturblock: allt efter "-- " eller "--" på egen rad
        if line.rstrip() == "-- " or line.rstrip() == "--":
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


def parse_email(
    raw: bytes,
    body_format: str = "text",
    max_length: int | None = 500,
) -> dict[str, Any]:
    msg = email.message_from_bytes(raw)
    body = get_body(msg)

    body_plain = body["plain"]
    body_html = body["html"]

    if body_format == "full":
        # Returnera råa body utan trunkering
        pass
    elif body_format == "text":
        # Om ingen plain text, strippa HTML-taggar som fallback
        if not body_plain and body_html:
            body_plain = _strip_html(body_html)
        body_plain = _truncate(body_plain, max_length)
    elif body_format == "stripped":
        if not body_plain and body_html:
            body_plain = _strip_html(body_html)
        body_plain = _strip_quotes_and_signature(body_plain)
        body_plain = _truncate(body_plain, max_length)

    return {
        "message_id": msg.get("Message-ID", ""),
        "subject": decode_header_value(msg.get("Subject")),
        "from": decode_header_value(msg.get("From")),
        "to": extract_addresses(msg.get("To")),
        "cc": extract_addresses(msg.get("Cc")),
        "bcc": extract_addresses(msg.get("Bcc")),
        "reply_to": extract_addresses(msg.get("Reply-To")),
        "date": msg.get("Date", ""),
        "body_plain": body_plain,
        "body_html": body_html,
        "attachments": get_attachments(msg),
        "headers": {k: decode_header_value(v) for k, v in msg.items()},
    }


def parse_envelope(envelope_data: str) -> dict[str, str]:
    """Parsar en IMAP ENVELOPE-sträng till ett enkelt dict med metadata."""
    # Returnerar rådata — full parsning görs av aioimaplib
    return {"raw": envelope_data}

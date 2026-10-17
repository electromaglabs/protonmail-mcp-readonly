import email
import email.header
import email.utils
import html
import re
from email.message import Message
from typing import Any

BODY_FORMATS = ("text", "stripped", "full")


def _safe_decode(payload: bytes, charset: str) -> str:
    """Decode payload with the given charset, falling back to utf-8 if it is unknown."""
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            # _safe_decode: a made-up charset name in a header must not crash the tool
            decoded.append(_safe_decode(part, charset or "utf-8"))
        else:
            decoded.append(part)
    return "".join(decoded)


def extract_addresses(header_value: str | None) -> list[str]:
    if not header_value:
        return []
    addresses = email.utils.getaddresses([header_value])
    return [f"{name} <{addr}>" if name else addr for name, addr in addresses]


def get_body(msg: Message) -> dict[str, str]:
    plain = ""
    html_body = ""

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
            elif content_type == "text/html" and not html_body:
                payload = part.get_payload(decode=True)
                if payload:
                    html_body = _safe_decode(payload, charset)
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            content_type = msg.get_content_type()
            if content_type == "text/html":
                html_body = _safe_decode(payload, charset)
            else:
                plain = _safe_decode(payload, charset)

    return {"plain": plain, "html": html_body}


def get_attachments(msg: Message) -> list[dict[str, Any]]:
    """Attachment names, types and sizes only. Attachment content is never returned."""
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


_NON_TEXT_BLOCK_RE = re.compile(r"<(script|style|head)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html_text: str) -> str:
    """Reduce HTML to plain text.

    Scripts, style sheets and comments are dropped along with the tags. This is
    not a security filter: text an email hides with styling still comes through.
    """
    text = _NON_TEXT_BLOCK_RE.sub("", html_text)
    text = _COMMENT_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()


def _strip_quotes_and_signature(text: str) -> str:
    """Remove quoted lines (starting with >) and the signature block (after '-- ')."""
    lines = text.splitlines()
    result = []
    for line in lines:
        # Signature block: everything after "-- " or "--" on its own line
        if line.rstrip() == "-- " or line.rstrip() == "--":
            break
        # Skip quoted lines
        if line.startswith(">"):
            continue
        result.append(line)
    return "\n".join(result)


def _truncate(text: str, max_length: int | None) -> str:
    """Cut text to max_length characters and say how much was left out."""
    if max_length is None or len(text) <= max_length:
        return text
    remaining = len(text) - max_length
    return text[:max_length] + f"\n[...{remaining} characters remaining]"


def parse_email(
    raw: bytes,
    body_format: str = "text",
    max_length: int | None = 500,
) -> dict[str, Any]:
    """Parse a raw message.

    "text" and "stripped" return a truncated plain-text body only: the raw HTML
    and the full header dump are left out, so max_length really does bound how
    much of the message is returned. "full" returns everything, untruncated.
    """
    if body_format not in BODY_FORMATS:
        raise ValueError(f"body_format must be one of {', '.join(BODY_FORMATS)}")
    if max_length is not None and max_length < 1:
        raise ValueError("max_length must be 1 or greater, or null for no limit")

    msg = email.message_from_bytes(raw)
    body = get_body(msg)

    body_plain = body["plain"]
    body_html = body["html"]
    headers: dict[str, str] = {}

    if body_format == "full":
        headers = dict(msg.items())
    else:
        # If there is no plain-text part, fall back to the HTML with tags removed
        if not body_plain and body_html:
            body_plain = _strip_html(body_html)
        if body_format == "stripped":
            body_plain = _strip_quotes_and_signature(body_plain)
        body_plain = _truncate(body_plain, max_length)
        body_html = ""

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
        "headers": headers,
    }

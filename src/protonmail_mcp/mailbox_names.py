"""Mappnamn i modified UTF-7 (RFC 3501 §5.1.3).

IMAP skickar mappnamn som 7-bitars ASCII. Utskrivbar ASCII (0x20–0x7E)
står för sig själv, utom "&" som skrivs "&-". Allt annat skrivs som
UTF-16BE i base64 mellan "&" och "-", med "," i stället för "/" och utan
"="-utfyllnad. "Näs" blir alltså "N&AOQ-s".
"""
import base64
import re

_B64_RE = re.compile(r"[A-Za-z0-9+,]+")


def _is_printable_ascii(ch: str) -> bool:
    return 0x20 <= ord(ch) <= 0x7E


def _b64_run(text: str) -> str:
    try:
        raw = text.encode("utf-16-be")
    except UnicodeEncodeError as e:
        raise ValueError(f"Ogiltigt tecken (ensam surrogat) i mappnamn: {text!r}") from e
    return "&" + base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",") + "-"


def encode_modified_utf7(name: str) -> str:
    """Kodar ett läsbart mappnamn till modified UTF-7."""
    out: list[str] = []
    run: list[str] = []
    for ch in name:
        if _is_printable_ascii(ch):
            if run:
                out.append(_b64_run("".join(run)))
                run.clear()
            out.append("&-" if ch == "&" else ch)
        else:
            run.append(ch)
    if run:
        out.append(_b64_run("".join(run)))
    return "".join(out)


def decode_modified_utf7(wire: str) -> str:
    """Avkodar ett mappnamn i modified UTF-7.

    Strikt: kastar ValueError om namnet inte är kanonisk modified UTF-7,
    så att encode_modified_utf7(decode_modified_utf7(x)) == x alltid gäller.
    """
    out: list[str] = []
    i = 0
    while i < len(wire):
        ch = wire[i]
        if not _is_printable_ascii(ch):
            raise ValueError(f"Inte modified UTF-7 (tecken utanför ASCII): {wire!r}")
        if ch != "&":
            out.append(ch)
            i += 1
            continue
        end = wire.find("-", i + 1)
        if end == -1:
            raise ValueError(f"Inte modified UTF-7 (saknar avslutande '-'): {wire!r}")
        chunk = wire[i + 1:end]
        if not chunk:
            out.append("&")
        else:
            if not _B64_RE.fullmatch(chunk):
                raise ValueError(f"Inte modified UTF-7 (ogiltig base64): {wire!r}")
            padded = chunk.replace(",", "/") + "=" * (-len(chunk) % 4)
            try:
                out.append(base64.b64decode(padded, validate=True).decode("utf-16-be"))
            except ValueError as e:  # binascii.Error och UnicodeDecodeError
                raise ValueError(f"Inte modified UTF-7 ({e}): {wire!r}") from e
        i = end + 1
    name = "".join(out)
    # Fångar allt som avkodas men inte är kanoniskt: base64-kodad utskrivbar
    # ASCII, intilliggande sekvenser och utfyllnadsbitar som inte är noll
    if encode_modified_utf7(name) != wire:
        raise ValueError(f"Inte kanonisk modified UTF-7: {wire!r}")
    return name

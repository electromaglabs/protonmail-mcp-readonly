"""Testverktyg för feat-bilagor: bilagekatalog i tmp och mejl med bilagor."""
from __future__ import annotations

import re

import pytest

from protonmail_mcp.config import get_settings


def unescape(text: str) -> str:
    """Tolka \\n, \\t, \\xNN och \\uNNNN i en sträng från en .feature-fil
    (Gherkin har inga escape-sekvenser) utan att röra åäö."""
    def repl(m: re.Match) -> str:
        token = m.group(0)
        if token == "\\n":
            return "\n"
        if token == "\\t":
            return "\t"
        if token == "\\\\":
            return "\\"
        return chr(int(token[2:], 16))

    return re.sub(r"\\u[0-9a-fA-F]{4}|\\x[0-9a-fA-F]{2}|\\n|\\t|\\\\", repl, text)


@pytest.fixture
def attachment_env(tmp_path, monkeypatch):
    """Sätt PROTONMAIL_ATTACHMENT_DIR till en tmp-katalog (som inte finns än)
    och returnera (katalog, katalog utanför). Inställningarna läses om."""
    root = tmp_path / "bilagor"
    outside = tmp_path / "utanfor"
    outside.mkdir()
    monkeypatch.setenv("PROTONMAIL_USERNAME", "me@proton.me")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pw")
    monkeypatch.setenv("PROTONMAIL_ATTACHMENT_DIR", str(root))
    get_settings.cache_clear()
    yield root, outside
    get_settings.cache_clear()


def multipart(*parts: str, boundary: str = "B") -> str:
    body = "".join(f"--{boundary}\r\n{p}\r\n" for p in parts)
    return f'Content-Type: multipart/mixed; boundary="{boundary}"\r\n\r\n{body}--{boundary}--\r\n'


def raw_message(body_and_type: str, subject: str = "Bilagor") -> bytes:
    return (
        "From: Anna <anna@example.se>\r\n"
        "To: me@proton.me\r\n"
        f"Subject: {subject}\r\n"
        "Date: Mon, 12 Oct 2026 09:30:00 +0200\r\n"
        "Message-ID: <bilagor-1@example.se>\r\n"
        "MIME-Version: 1.0\r\n"
        f"{body_and_type}"
    ).encode("utf-8")


def text_part(text: str = "Hej, se bilagan.") -> str:
    return f"Content-Type: text/plain; charset=utf-8\r\n\r\n{text}"


def base64_part(content_type: str, filename_params: str, data: bytes) -> str:
    import base64

    encoded = base64.encodebytes(data).decode("ascii").replace("\n", "\r\n").rstrip()
    return (
        f"Content-Type: {content_type}\r\n"
        "Content-Transfer-Encoding: base64\r\n"
        f"Content-Disposition: attachment{filename_params}\r\n\r\n{encoded}"
    )

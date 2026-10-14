"""Enhetstester för fix-svar: reply_to_email och forward_email."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.tools.reply import forward_email, reply_to_email
from tests.fix_svar_support import KONTO, capture_smtp, header_addresses, make_client


def _ctx(raw: bytes | None, account: str = KONTO):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()
    app.imap.get_message.return_value = raw
    app.smtp = make_client(account)
    return ctx


def _raw(headers: str, body: str = "Originaltext\r\n", content_type="text/plain; charset=utf-8") -> bytes:
    head = headers.strip().replace("\n", "\r\n")
    return (
        f"{head}\r\nContent-Type: {content_type}\r\n\r\n{body}"
    ).encode("utf-8")


# -------------------------------------------------------------------
# B8: ett enda Re:/Fwd:-prefix
# -------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("SV: möte", "Re: möte"),
        ("sv:möte", "Re: möte"),
        ("Re: Re: Re: möte", "Re: möte"),
        ("AW: WG: möte", "Re: WG: möte"),  # WG är inte i listan — lämnas orört
        ("Re [3] : möte", "Re: möte"),
        ("Svar: möte", "Re: Svar: möte"),  # "Svar" är inget prefix
        ("Vs. budget", "Re: Vs. budget"),
        ("  SV:   möte  ", "Re: möte"),
    ],
)
async def test_reply_subject_prefix_normalized(subject, expected):
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: {subject}\nMessage-ID: <m@x.se>")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert str(cap.parsed["Subject"]) == expected


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("möte", "Fwd: möte"),
        ("Fwd: Fwd: möte", "Fwd: möte"),
        ("VB: möte", "Fwd: möte"),
        ("SV: möte", "Fwd: möte"),
        ("Fw: Re: möte", "Fwd: möte"),
    ],
)
async def test_forward_subject_prefix_normalized(subject, expected):
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: {subject}\nMessage-ID: <m@x.se>")
    with capture_smtp() as cap:
        await forward_email(_ctx(raw), uid="1", to="b@x.se")
    assert str(cap.parsed["Subject"]) == expected


async def test_reply_subject_from_raw_utf8_header_is_not_mojibake():
    raw = (
        "From: Åsa Öberg <a@x.se>\r\nTo: me@proton.me\r\nSubject: SV: möte\r\n"
        "Message-ID: <m@x.se>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nx\r\n"
    ).encode("utf-8")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert str(cap.parsed["Subject"]) == "Re: möte"


async def test_reply_subject_with_encoded_linebreak_is_flattened():
    raw = _raw(
        "From: a@x.se\nTo: me@proton.me\nSubject: =?utf-8?q?m=C3=B6te=0D=0ABcc=3A_evil@e.com?=\n"
        "Message-ID: <m@x.se>"
    )
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert str(cap.parsed["Subject"]) == "Re: möte Bcc: evil@e.com"
    assert cap.parsed["Bcc"] is None
    assert cap.recipients == ["a@x.se"]

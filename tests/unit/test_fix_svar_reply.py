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


# -------------------------------------------------------------------
# B5: References läses skiftlägesokänsligt och bara som msg-id:n
# -------------------------------------------------------------------


@pytest.mark.parametrize("name", ["References", "references", "REFERENCES"])
async def test_references_any_case_is_chained(name):
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s\nMessage-ID: <m3@x>\n{name}: <m1@x>\n <m2@x>")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert str(cap.parsed["In-Reply-To"]) == "<m3@x>"
    assert " ".join(str(cap.parsed["References"]).split()) == "<m1@x> <m2@x> <m3@x>"


async def test_references_keeps_only_message_ids_and_dedupes():
    raw = _raw(
        f"From: a@x.se\nTo: {KONTO}\nSubject: s\nMessage-ID: <m3@x>\n"
        "References: =?utf-8?q?skr=C3=A4p?= <m1@x> junk <m1@x> <m3@x>"
    )
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert " ".join(str(cap.parsed["References"]).split()) == "<m1@x> <m3@x>"


async def test_in_reply_to_used_when_references_missing():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s\nMessage-ID: <m2@x>\nIn-Reply-To: <m1@x>")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert " ".join(str(cap.parsed["References"]).split()) == "<m1@x> <m2@x>"


async def test_no_message_id_means_no_threading_headers():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert cap.parsed["In-Reply-To"] is None
    assert cap.parsed["References"] is None


# -------------------------------------------------------------------
# Säkerhetsgranskning: originalets headers styrs av avsändaren och får
# inte kunna låsa servern (kvadratisk regex eller parsning)
# -------------------------------------------------------------------


def _elapsed(fn) -> float:
    import time

    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def test_prefix_stripping_is_linear_on_whitespace_runs():
    from protonmail_mcp.tools.reply import _base_subject

    assert _elapsed(lambda: _base_subject("re" + " " * 50_000 + "x")) < 0.2


def test_prefix_stripping_is_linear_on_many_prefixes():
    from protonmail_mcp.tools.reply import _base_subject

    assert _base_subject("re: " * 50_000 + "x") == "x"
    assert _elapsed(lambda: _base_subject("re: " * 50_000 + "x")) < 0.2


async def test_huge_references_header_is_cheap_and_trimmed():
    refs = " ".join(f"<r{i}@x.se>" for i in range(50_000))
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s\nMessage-ID: <m@x>\nReferences: {refs}")
    import time

    with capture_smtp() as cap:
        start = time.perf_counter()
        await reply_to_email(_ctx(raw), uid="1", body="ok")
        assert time.perf_counter() - start < 1.0
    ids = str(cap.parsed["References"]).split()
    # Första id:t (trådens rot) och de senaste behålls, och svarets id sist
    assert ids[0] == "<r0@x.se>" and ids[-1] == "<m@x>" and len(ids) <= 50


async def test_huge_subject_is_cheap():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: " + "möte " * 200_000 + "\nMessage-ID: <m@x>")
    import time

    with capture_smtp():
        start = time.perf_counter()
        try:
            await reply_to_email(_ctx(raw), uid="1", body="ok")
        except ValueError:
            pass  # ett orimligt ämne får avvisas, men snabbt
        assert time.perf_counter() - start < 1.0

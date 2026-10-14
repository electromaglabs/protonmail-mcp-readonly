"""Säkerhetsgranskning av reply.py: originalets headers styrs av avsändaren
och får inte kunna låsa MCP-servern."""
from __future__ import annotations

import pytest

from protonmail_mcp.tools.reply import reply_to_email
from tests.fix_svar_support import KONTO, capture_smtp
from tests.unit.test_fix_svar_reply import _ctx, _raw


async def test_header_cap_cannot_be_defeated_by_repeating_the_header():
    """Säkerhetsgranskning: gränsen gäller summan av alla förekomster."""
    import time

    chunk = ", ".join(f"=?utf-8?q?=C3=85sa_{i}?= <a{i}@x.se>" for i in range(1_300))
    assert len(chunk) < 50_000
    headers = "".join(f"Cc: {chunk}\n" for _ in range(40))
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\n{headers}Subject: s")
    with capture_smtp() as cap:
        start = time.perf_counter()
        with pytest.raises(ValueError, match="orimligt"):
            await reply_to_email(_ctx(raw), mailbox="INBOX", uid="1", body="ok", reply_all=True)
        assert time.perf_counter() - start < 1.0
    assert cap.sent == []


@pytest.mark.parametrize("pattern", ["<body", "<a", "<style>", "<aaaaaaaaaa", "cid:"])
@pytest.mark.parametrize("tool", ["reply", "forward"])
async def test_html_only_original_is_handled_in_linear_time(pattern, tool):
    """email_parser._strip_html (<[^>]+>) är kvadratisk på "<body<body…";
    svar och vidarebefordran får inte låsa servern på ett sådant HTML-brev."""
    import time

    from protonmail_mcp.tools.reply import forward_email

    html = pattern * (300_000 // len(pattern))
    raw = (
        f"From: a@x.se\r\nTo: {KONTO}\r\nSubject: s\r\nContent-Type: text/html\r\n\r\n{html}\r\n"
    ).encode()
    with capture_smtp():
        start = time.perf_counter()
        if tool == "reply":
            await reply_to_email(_ctx(raw), mailbox="INBOX", uid="1", body="ok")
        else:
            await forward_email(_ctx(raw), mailbox="INBOX", uid="1", to="b@x.se")
        assert time.perf_counter() - start < 1.0


@pytest.mark.parametrize("tool", ["reply", "forward"])
async def test_huge_headers_spread_over_mime_parts_are_rejected_fast(tool):
    """Headerparsern i email.policy är superlinjär; varje MIME-del har egna
    headers (Content-Type m.fl.) som också styrs av avsändaren."""
    import time

    from protonmail_mcp.tools.reply import forward_email

    param = "a" * 45_000
    parts = "".join(
        f'--B\r\nContent-Type: application/octet-stream; x="{param}"\r\n\r\nx\r\n'
        for _ in range(60)
    )
    raw = (
        f"From: a@x.se\r\nTo: {KONTO}\r\nSubject: s\r\n"
        'Content-Type: multipart/mixed; boundary="B"\r\n\r\n'
        f"--B\r\nContent-Type: text/plain\r\n\r\nhej\r\n{parts}--B--\r\n"
    ).encode()
    with capture_smtp() as cap:
        start = time.perf_counter()
        with pytest.raises(ValueError, match="orimligt"):
            if tool == "reply":
                await reply_to_email(_ctx(raw), mailbox="INBOX", uid="1", body="ok")
            else:
                await forward_email(_ctx(raw), mailbox="INBOX", uid="1", to="b@x.se")
        assert time.perf_counter() - start < 1.0
    assert cap.sent == []


@pytest.mark.parametrize("tool", ["reply", "forward"])
async def test_huge_number_of_mime_parts_is_rejected_fast(tool):
    """Varje del parsas (Content-Type) med email.policy; 20 000 små delar
    tog flera sekunder innan något skickades."""
    import time

    from protonmail_mcp.tools.reply import forward_email

    parts = "".join(
        f"--B\r\nContent-Type: application/octet-stream\r\n\r\n{i}\r\n" for i in range(20_000)
    )
    raw = (
        f"From: a@x.se\r\nTo: {KONTO}\r\nSubject: s\r\n"
        'Content-Type: multipart/mixed; boundary="B"\r\n\r\n'
        f"--B\r\nContent-Type: text/plain\r\n\r\nhej\r\n{parts}--B--\r\n"
    ).encode()
    with capture_smtp() as cap:
        start = time.perf_counter()
        with pytest.raises(ValueError, match="delar"):
            if tool == "reply":
                await reply_to_email(_ctx(raw), mailbox="INBOX", uid="1", body="ok")
            else:
                await forward_email(_ctx(raw), mailbox="INBOX", uid="1", to="b@x.se")
        assert time.perf_counter() - start < 1.0
    assert cap.sent == []


async def test_normal_number_of_attachments_still_forwarded():
    from protonmail_mcp.tools.reply import forward_email

    parts = "".join(
        f"--B\r\nContent-Type: application/octet-stream\r\n"
        f"Content-Disposition: attachment; filename=f{i}.bin\r\n\r\n{i}\r\n"
        for i in range(200)
    )
    raw = (
        f"From: a@x.se\r\nTo: {KONTO}\r\nSubject: s\r\n"
        'Content-Type: multipart/mixed; boundary="B"\r\n\r\n'
        f"--B\r\nContent-Type: text/plain\r\n\r\nhej\r\n{parts}--B--\r\n"
    ).encode()
    with capture_smtp() as cap:
        await forward_email(_ctx(raw), mailbox="INBOX", uid="1", to="b@x.se")
    assert len(list(cap.parsed.iter_attachments())) == 200


# --- Granskning 2: parsning/ombrytning av headers i MIME-delar ----------


def _mixed(parts: str) -> bytes:
    return (
        f"From: a@x.se\r\nTo: {KONTO}\r\nSubject: s\r\n"
        'Content-Type: multipart/mixed; boundary="B"\r\n\r\n'
        f"--B\r\nContent-Type: text/plain\r\n\r\nhej\r\n{parts}--B--\r\n"
    ).encode()


async def _timed(tool, raw, cap):
    """Tid för verktyget inklusive serialiseringen, som aiosmtplib gör vid
    sändning (attrappen gör den inte själv)."""
    import time

    from protonmail_mcp.tools.reply import forward_email

    start = time.perf_counter()
    try:
        if tool == "reply":
            await reply_to_email(_ctx(raw), mailbox="INBOX", uid="1", body="ok")
        else:
            await forward_email(_ctx(raw), mailbox="INBOX", uid="1", to="b@x.se")
        cap.raw
    except ValueError as exc:
        assert "orimligt" in str(exc)
    return time.perf_counter() - start


async def test_long_non_mime_header_in_attachment_is_not_refolded_slowly():
    """Bifogade delar bryts om av generatorn med den superlinjära parsern."""
    part = f"--B\r\nContent-Type: application/octet-stream\r\nX-Junk: {'a ' * 200_000}\r\n\r\nx\r\n"
    with capture_smtp() as cap:
        assert await _timed("forward", _mixed(part), cap) < 1.0


@pytest.mark.parametrize("tool", ["reply", "forward"])
async def test_content_type_with_comments_in_many_parts_is_cheap(tool):
    ctype = "application/octet-stream; x=y " + "(a)" * 3_300
    parts = "".join(f"--B\r\nContent-Type: {ctype}\r\n\r\nx\r\n" for _ in range(95))
    with capture_smtp() as cap:
        assert await _timed(tool, _mixed(parts), cap) < 1.0


@pytest.mark.parametrize("tool", ["reply", "forward"])
async def test_address_header_with_many_comments_is_cheap(tool):
    raw = (
        f"From: a@x.se {'(a)' * 16_600}\r\nTo: {KONTO}\r\nSubject: s\r\n"
        "Content-Type: text/plain\r\n\r\nhej\r\n"
    ).encode()
    with capture_smtp() as cap:
        assert await _timed(tool, raw, cap) < 1.0


@pytest.mark.parametrize("tool", ["reply", "forward"])
async def test_deep_nesting_gives_clear_error_not_recursion_error(tool):
    depth = 990
    raw = f"From: a@x.se\r\nTo: {KONTO}\r\nSubject: s\r\n"
    raw += 'Content-Type: multipart/mixed; boundary="b0"\r\n\r\n'
    for i in range(1, depth):
        raw += f'--b{i-1}\r\nContent-Type: multipart/mixed; boundary="b{i}"\r\n\r\n'
    raw += f"--b{depth-1}\r\nContent-Type: text/plain\r\n\r\nhej\r\n--b{depth-1}--\r\n"
    for i in range(depth - 2, -1, -1):
        raw += f"--b{i}--\r\n"
    from protonmail_mcp.tools.reply import forward_email

    with capture_smtp():
        with pytest.raises(ValueError, match="nästlat"):
            if tool == "reply":
                await reply_to_email(_ctx(raw.encode()), mailbox="INBOX", uid="1", body="ok")
            else:
                await forward_email(_ctx(raw.encode()), mailbox="INBOX", uid="1", to="b@x.se")

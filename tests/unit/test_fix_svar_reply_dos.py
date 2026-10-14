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
            await reply_to_email(_ctx(raw), uid="1", body="ok", reply_all=True)
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
            await reply_to_email(_ctx(raw), uid="1", body="ok")
        else:
            await forward_email(_ctx(raw), uid="1", to="b@x.se")
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
                await reply_to_email(_ctx(raw), uid="1", body="ok")
            else:
                await forward_email(_ctx(raw), uid="1", to="b@x.se")
        assert time.perf_counter() - start < 1.0
    assert cap.sent == []

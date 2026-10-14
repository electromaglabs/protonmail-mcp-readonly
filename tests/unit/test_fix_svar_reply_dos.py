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

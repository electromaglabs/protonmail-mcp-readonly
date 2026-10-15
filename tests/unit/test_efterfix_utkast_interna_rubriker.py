"""Enhetstester: send_draft skickar inte Protons interna X-Pm-*-rubriker."""
import email
import email.policy

import pytest

from tests.fix_svar_support import capture_smtp, make_client

RAW = (
    b"From: me@proton.me\r\nTo: a@example.se\r\nSubject: s\r\n"
    b"Message-ID: <abc==@protonmail.internalid>\r\n"
    b"X-Pm-Internal-Id: abc==\r\nX-PM-Gluon-Id: 42\r\nx-pm-date: Mon, 12 Oct 2026 09:30:00 +0000\r\n"
    b"X-Pm-Origin: internal\r\nX-Pm-Content-Encryption: end-to-end\r\n"
    b"X-Pmx-Annat: behalls\r\n"
    b"References: <p@example.se> <abc==@protonmail.internalid>\r\n\r\nText\r\n"
)


class TestInternalHeaders:
    @pytest.mark.asyncio
    async def test_x_pm_headers_are_removed_from_what_is_sent(self):
        msg = email.message_from_bytes(RAW, policy=email.policy.SMTP)
        with capture_smtp() as cap:
            await make_client().send_prepared_message(msg)
        sent = cap.parsed
        assert [k for k in sent.keys() if k.lower().startswith("x-pm-")] == []
        assert b"x-pm-" not in cap.raw.lower()
        # Bara exakt prefixet "X-Pm-" räknas som Protons
        assert sent["X-Pmx-Annat"] == "behalls"
        # Bridge behöver referensen för att hitta (och ta bort) utkastet
        assert sent["References"] == "<p@example.se> <abc==@protonmail.internalid>"
        # Meddelandet som skickades in ändras inte
        assert msg["X-Pm-Internal-Id"] == "abc=="

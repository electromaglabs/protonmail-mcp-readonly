"""Säkerhetsnotering (reply.py): ett förfalskat mejl med From = det egna kontot är inte "eget".

Ett eget skickat mejl får svaret till sina mottagare (To/Cc). Det gäller nu
bara när mejlet bevisligen kommer från kontot: Bridge märker det
`X-Pm-Origin: internal` (live: alla 153 egna mejl i Sent, aldrig ett externt
mejl), eller så finns samma Proton-mejl (X-Pm-Internal-Id) i Sent. Annars
behandlas det som ett vanligt mottaget mejl: svaret går till Reply-To/From.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from protonmail_mcp.tools.reply import build_reply
from tests.efterfix_slut_bridge import make_client

ME = "me@proton.me"
LOOKALIKE = "ekonomi@pr0ton-me.com"


def _raw(*extra: str, from_: str = ME, to: str = LOOKALIKE) -> bytes:
    lines = [f"From: {from_}", f"To: {to}", *extra, "Subject: Faktura", "Message-ID: <f@evil>", "", "Hej"]
    return "\r\n".join(lines).encode()


@pytest.fixture
def app(monkeypatch):
    imap, bridge = make_client(monkeypatch)
    imap.get_message = AsyncMock()
    return SimpleNamespace(imap=imap, smtp=SimpleNamespace(account_address=ME), bridge=bridge)


async def _to(app, raw: bytes) -> list[str]:
    app.imap.get_message.return_value = raw
    fields = await build_reply(app, "3", "INBOX", "Svar")
    return fields["to"]


class TestForgedFromOwnAccount:
    async def test_external_forgery_does_not_reply_to_its_to(self, app):
        to = await _to(app, _raw("X-Pm-Origin: external", "X-Pm-Internal-Id: forged1"))
        assert LOOKALIKE not in to
        assert to == [ME]

    async def test_forgery_with_reply_to_goes_to_reply_to_as_usual(self, app):
        to = await _to(app, _raw("X-Pm-Origin: external", "Reply-To: x@evil.example"))
        assert to == ["x@evil.example"]

    async def test_no_proton_headers_is_not_own(self, app):
        assert await _to(app, _raw()) == [ME]

    async def test_repeated_origin_header_is_not_trusted(self, app):
        raw = _raw("X-Pm-Origin: internal", "X-Pm-Origin: external", "X-Pm-Internal-Id: forged1")
        assert await _to(app, raw) == [ME]

    async def test_internal_id_not_in_sent_is_not_own(self, app):
        app.bridge.put("Sent", "1", "<other@proton.me>")
        assert await _to(app, _raw("X-Pm-Internal-Id: forged1")) == [ME]


class TestGenuineOwnMail:
    async def test_marked_internal_replies_to_its_recipients(self, app):
        assert await _to(app, _raw("X-Pm-Origin: internal")) == [LOOKALIKE]
        assert not app.bridge.sent("SELECT")  # rubriken räcker, ingen sökning

    async def test_found_in_sent_replies_to_its_recipients(self, app):
        key = "<mine@proton.me>"
        app.bridge.put("Sent", "1", key)
        raw = _raw(f"X-Pm-Internal-Id: {app.bridge.internal_id(key)}", to="anna@example.com")
        assert await _to(app, raw) == ["anna@example.com"]
        assert ("SELECT", "Sent") in app.bridge.commands

    async def test_sent_lookup_failing_is_not_own(self, app):
        key = "<mine@proton.me>"
        app.bridge.put("Sent", "1", key)
        app.bridge.client.search.side_effect = asyncio.TimeoutError()
        raw = _raw(f"X-Pm-Internal-Id: {app.bridge.internal_id(key)}", to="anna@example.com")
        assert await _to(app, raw) == [ME]


class TestOtherSendersUntouched:
    async def test_no_lookup_for_other_senders(self, app):
        raw = _raw("X-Pm-Internal-Id: abc", from_="anna@example.com", to=ME)
        assert await _to(app, raw) == ["anna@example.com"]
        assert not app.bridge.commands

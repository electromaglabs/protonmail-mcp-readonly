"""Enhetstester: update_draft behåller trådning och bilagor och flyttar det gamla till Trash."""
import asyncio
import email
import email.policy
from email.message import EmailMessage
from unittest.mock import MagicMock

import aioimaplib
import pytest

from protonmail_mcp import imap_drafts
from protonmail_mcp.tools import drafts
from tests.feat_utkast_bridge import make_imap
from tests.fix_svar_support import make_client

RAW = (
    b"From: me@proton.me\r\nTo: a@example.se\r\nSubject: Hej\r\n"
    b"Message-ID: <abc@proton.me>\r\n\r\nText\r\n"
)


def _ctx(imap):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.smtp = make_client("me@proton.me")
    app.imap = imap
    return ctx


def _parse(raw: bytes):
    return email.message_from_bytes(raw, policy=email.policy.default)


async def _update(imap, uid, **fields):
    fields = {"to": "a@example.se", "subject": "Ny", "body": "Ny text", **fields}
    return await drafts.update_draft(_ctx(imap), uid=uid, mailbox="Drafts", **fields)


class TestReplaceDraftMovesToTrash:
    @pytest.mark.asyncio
    async def test_refused_move_names_both_drafts(self):
        imap, bridge = make_imap()
        old = bridge.add("Drafts", b"Subject: gammal\r\n\r\nx\r\n")
        bridge.refuse["MOVE"] = "move failed"
        with pytest.raises(ValueError) as excinfo:
            await imap_drafts.replace_draft(imap, old, RAW, "<abc@proton.me>")
        text = str(excinfo.value)
        assert "UID 2" in text and f"UID {old}" in text and "<abc@proton.me>" in text
        assert sorted(bridge.messages("Drafts")) == [int(old), 2]


class TestUpdateDraftKeepsParts:
    @pytest.mark.asyncio
    async def test_attached_message_and_files_follow_byte_for_byte(self):
        imap, bridge = make_imap()
        inner = EmailMessage()
        inner["Subject"] = "Bifogat mejl"
        inner.set_content("inre")
        old = EmailMessage()
        old["From"] = "me@proton.me"
        old["To"] = "a@example.se"
        old["Subject"] = "Gammal"
        old.set_content("Gammal text")
        old.add_attachment(b"\x00\x01binar", maintype="application", subtype="octet-stream",
                           filename="data.bin")
        old.add_attachment(inner)
        uid = bridge.add("Drafts", old.as_bytes(), ("\\Draft", "\\Seen"))

        result = await _update(imap, uid)

        new = _parse(bridge.messages("Drafts")[int(result["uid"])]["raw"])
        parts = list(new.iter_attachments())
        assert [p.get_content_type() for p in parts] == ["application/octet-stream",
                                                        "message/rfc822"]
        assert parts[0].get_content() == b"\x00\x01binar"
        assert parts[1].get_content()["Subject"] == "Bifogat mejl"
        assert "Ny text" in new.get_body(("plain",)).get_content()
        assert "Gammal text" not in new.as_string()
        assert result["kept_attachments"] == ["data.bin", "message/rfc822"]
        assert result["kept_headers"] == []

    @pytest.mark.asyncio
    async def test_only_message_ids_are_carried_over_from_thread_headers(self):
        imap, bridge = make_imap()
        raw = (
            b"From: me@proton.me\r\nTo: a@example.se\r\nSubject: Re: x\r\n"
            b"In-Reply-To: <p@example.se> skrap\r\n"
            b"References: <r1@example.se> =?utf-8?q?Bcc=3A_evil=40x=2Ese?= <p@example.se>\r\n"
            b"\r\nText\r\n"
        )
        uid = bridge.add("Drafts", raw, ("\\Draft", "\\Seen"))
        result = await _update(imap, uid)
        new = _parse(bridge.messages("Drafts")[int(result["uid"])]["raw"])
        assert new["In-Reply-To"] == "<p@example.se>"
        assert new["References"] == "<r1@example.se> <p@example.se>"
        assert new["Bcc"] is None
        assert result["kept_headers"] == ["In-Reply-To", "References"]

    @pytest.mark.asyncio
    async def test_missing_draft_changes_nothing(self):
        imap, bridge = make_imap()
        with pytest.raises(ValueError, match="Inget meddelande med UID 7 i Drafts"):
            await _update(imap, "7")
        assert "APPEND" not in bridge.names()

    @pytest.mark.asyncio
    async def test_invalid_address_changes_nothing(self):
        imap, bridge = make_imap()
        uid = bridge.add("Drafts", RAW, ("\\Draft", "\\Seen"))
        with pytest.raises(ValueError, match="Ogiltig e-postadress"):
            await _update(imap, uid, to="inte-en-adress")
        assert "APPEND" not in bridge.names() and "UID MOVE" not in bridge.names()
        assert list(bridge.messages("Drafts")) == [int(uid)]


class TestReplaceDraftInterrupted:
    """K4: avbrott när det gamla utkastet flyttas efter att det nya sparats."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", [
        asyncio.TimeoutError(),
        ConnectionResetError("Connection lost"),
        aioimaplib.AioImapException("protokollfel"),
    ], ids=["timeout", "anslutning", "aioimaplib"])
    async def test_error_says_new_draft_exists_and_drops_connection(self, error):
        imap, bridge = make_imap()
        old = bridge.add("Drafts", b"Subject: gammal\r\n\r\nx\r\n")
        inner = bridge.client.uid.side_effect

        async def uid(command, *args):
            if command.upper() == "MOVE":
                raise error
            return await inner(command, *args)

        bridge.client.uid.side_effect = uid
        with pytest.raises(ValueError) as excinfo:
            await imap_drafts.replace_draft(imap, old, RAW, "<abc@proton.me>")
        text = str(excinfo.value)
        assert "Det nya utkastet sparades i Drafts (UID 2, Message-ID <abc@proton.me>)" in text
        assert f"UID {old}" in text and "Kör inte update_draft igen" in text
        assert isinstance(excinfo.value.__cause__, type(error))
        # Protokollets tillstånd är okänt efter avbrottet: nästa anrop ansluter på nytt
        assert imap._client is None

    @pytest.mark.asyncio
    async def test_cancellation_is_not_rewritten(self):
        imap, bridge = make_imap()
        old = bridge.add("Drafts", b"Subject: gammal\r\n\r\nx\r\n")
        inner = bridge.client.uid.side_effect

        async def uid(command, *args):
            if command.upper() == "MOVE":
                raise asyncio.CancelledError()
            return await inner(command, *args)

        bridge.client.uid.side_effect = uid
        with pytest.raises(asyncio.CancelledError):
            await imap_drafts.replace_draft(imap, old, RAW, "<abc@proton.me>")

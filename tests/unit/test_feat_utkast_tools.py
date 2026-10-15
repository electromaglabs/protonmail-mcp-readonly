"""Enhetstester för utkastverktygen (feat-utkast)."""
import email
import email.policy
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.tools import drafts
from tests.fix_svar_support import make_client


def _ctx():
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.smtp = make_client("me@proton.me")
    app.imap = MagicMock()
    return ctx, app


def _appended(monkeypatch):
    """Fånga det som skulle läggas i Drafts."""
    saved = {}

    async def fake_append(imap, raw, message_id):
        saved["raw"] = raw
        saved["message_id"] = message_id
        return "42"

    monkeypatch.setattr(drafts.imap_drafts, "append_draft", fake_append)
    return saved


def _parse(raw: bytes):
    return email.message_from_bytes(raw, policy=email.policy.default)


class TestCreateDraft:
    @pytest.mark.asyncio
    async def test_built_like_send_email(self, monkeypatch):
        saved = _appended(monkeypatch)
        ctx, _ = _ctx()
        result = await drafts.create_draft(
            ctx, to=["a@example.se", "Örjan <o@example.se>"], subject="Ämne",
            body="Hej", body_html="<p>Hej</p>", cc="c@example.se",
            reply_to="svar@example.se",
        )
        msg = _parse(saved["raw"])
        assert msg["From"] == "me@proton.me"
        assert [a.addr_spec for a in msg["To"].addresses] == ["a@example.se", "o@example.se"]
        assert msg["Cc"] == "c@example.se"
        assert msg["Reply-To"] == "svar@example.se"
        assert msg["Subject"] == "Ämne"
        assert msg["Date"]
        # Message-ID med kontots domän, inte maskinens värdnamn
        assert msg["Message-ID"].endswith("@proton.me>")
        assert msg.get_body(("html",)).get_content().strip() == "<p>Hej</p>"
        assert b"\r\n" in saved["raw"]
        assert result == {"uid": "42", "mailbox": "Drafts", "message_id": msg["Message-ID"]}
        assert saved["message_id"] == msg["Message-ID"]

    @pytest.mark.asyncio
    async def test_bcc_is_kept_in_the_draft(self, monkeypatch):
        saved = _appended(monkeypatch)
        ctx, _ = _ctx()
        await drafts.create_draft(ctx, to="a@example.se", subject="s", body="b",
                                  bcc=["h1@example.se", "Hemlig <h2@example.se>"])
        msg = _parse(saved["raw"])
        assert [a.addr_spec for a in msg["Bcc"].addresses] == ["h1@example.se", "h2@example.se"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["to", "cc", "bcc", "reply_to"])
    async def test_invalid_address_is_rejected_before_append(self, monkeypatch, field):
        saved = _appended(monkeypatch)
        ctx, _ = _ctx()
        kwargs = {"to": "a@example.se", "subject": "s", "body": "b", field: "x@y.se\r\nBcc: z@q.se"}
        with pytest.raises(ValueError, match="Ogiltig e-postadress"):
            await drafts.create_draft(ctx, **kwargs)
        assert saved == {}

    @pytest.mark.asyncio
    async def test_subject_with_newline_is_rejected(self, monkeypatch):
        saved = _appended(monkeypatch)
        ctx, _ = _ctx()
        with pytest.raises(ValueError, match="radbrytningar"):
            await drafts.create_draft(ctx, to="a@example.se", subject="a\nBcc: x@y.se", body="b")
        assert saved == {}

    @pytest.mark.asyncio
    async def test_unknown_uid_gives_a_hint(self, monkeypatch):
        async def fake_append(imap, raw, message_id):
            return None

        monkeypatch.setattr(drafts.imap_drafts, "append_draft", fake_append)
        ctx, _ = _ctx()
        result = await drafts.create_draft(ctx, to="a@example.se", subject="s", body="b")
        assert result["uid"] is None
        assert result["mailbox"] == "Drafts"
        assert "list_emails" in result["note"]

    @pytest.mark.asyncio
    async def test_nothing_is_sent(self, monkeypatch):
        _appended(monkeypatch)
        ctx, app = _ctx()
        app.smtp.send_email = AsyncMock()
        await drafts.create_draft(ctx, to="a@example.se", subject="s", body="b")
        app.smtp.send_email.assert_not_called()


ORIGINAL = (
    b"From: Anna Ek <anna@example.se>\r\nTo: me@proton.me\r\nSubject: M\xc3\xb6te\r\n"
    b"Message-ID: <orig-1@example.se>\r\nDate: Mon, 12 Oct 2026 09:30:00 +0200\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n\r\nOriginaltext\r\n"
)


def _ctx_with_original(raw=ORIGINAL):
    ctx, app = _ctx()
    app.imap.get_message = AsyncMock(return_value=raw)
    return ctx, app


class TestReplyDraft:
    @pytest.mark.asyncio
    async def test_reads_from_the_given_mailbox_and_keeps_bcc(self, monkeypatch):
        saved = _appended(monkeypatch)
        ctx, app = _ctx_with_original()
        result = await drafts.create_reply_draft(
            ctx, uid="7", mailbox="Archive", body="Svar", bcc="h@example.se",
            quote_original=False,
        )
        app.imap.get_message.assert_awaited_once_with("Archive", "7")
        msg = _parse(saved["raw"])
        assert msg["Subject"] == "Re: Möte"
        assert msg["Bcc"] == "h@example.se"
        assert msg["In-Reply-To"] == "<orig-1@example.se>"
        assert msg.get_body(("plain",)).get_content().strip() == "Svar"
        assert result["mailbox"] == "Drafts" and result["uid"] == "42"

    @pytest.mark.asyncio
    async def test_html_reply_quotes_original(self, monkeypatch):
        saved = _appended(monkeypatch)
        ctx, _ = _ctx_with_original()
        await drafts.create_reply_draft(
            ctx, uid="7", mailbox="INBOX", body="Svar", body_html="<p>Svar</p>",
        )
        html = _parse(saved["raw"]).get_body(("html",)).get_content()
        assert "<p>Svar</p>" in html and "blockquote" in html and "Originaltext" in html

    @pytest.mark.asyncio
    async def test_missing_original_raises_and_saves_nothing(self, monkeypatch):
        saved = _appended(monkeypatch)
        ctx, _ = _ctx_with_original(raw=None)
        with pytest.raises(ValueError, match="Inget meddelande med UID 7 i INBOX"):
            await drafts.create_reply_draft(ctx, uid="7", mailbox="INBOX", body="x")
        assert saved == {}


class TestForwardDraft:
    @pytest.mark.asyncio
    async def test_forward_draft_with_cc_and_bcc(self, monkeypatch):
        saved = _appended(monkeypatch)
        ctx, app = _ctx_with_original()
        await drafts.create_forward_draft(
            ctx, uid="7", mailbox="INBOX", to="bob@example.com",
            cc="c@example.se", bcc="h@example.se",
        )
        msg = _parse(saved["raw"])
        assert msg["Subject"] == "Fwd: Möte"
        assert msg["To"] == "bob@example.com"
        assert msg["Cc"] == "c@example.se"
        assert msg["Bcc"] == "h@example.se"
        assert "Originaltext" in msg.get_body(("plain",)).get_content()

    @pytest.mark.asyncio
    async def test_missing_original_raises(self, monkeypatch):
        saved = _appended(monkeypatch)
        ctx, _ = _ctx_with_original(raw=None)
        with pytest.raises(ValueError, match="Inget meddelande med UID 7 i INBOX"):
            await drafts.create_forward_draft(ctx, uid="7", mailbox="INBOX", to="b@example.com")
        assert saved == {}


class TestUpdateDraft:
    @pytest.mark.asyncio
    async def test_only_drafts_mailbox(self, monkeypatch):
        replaced = []

        async def fake_replace(*args):
            replaced.append(args)

        monkeypatch.setattr(drafts.imap_drafts, "replace_draft", fake_replace)
        ctx, _ = _ctx()
        with pytest.raises(ValueError, match="Bara utkast i Drafts"):
            await drafts.update_draft(ctx, uid="3", mailbox="INBOX", to="a@example.se",
                                      subject="s", body="b")
        assert replaced == []

    @pytest.mark.asyncio
    async def test_result_names_new_and_replaced_uid(self, monkeypatch):
        seen = {}

        async def fake_replace(imap, old_uid, raw, message_id):
            seen.update(old_uid=old_uid, raw=raw, message_id=message_id)
            return "9"

        monkeypatch.setattr(drafts.imap_drafts, "replace_draft", fake_replace)
        ctx, app = _ctx()
        # efterfix-utkast: det gamla utkastet läses först, och svaret anger vad som behölls
        app.imap.get_message = AsyncMock(
            return_value=b"To: a@example.se\r\nSubject: Gammal\r\n\r\nx\r\n"
        )
        result = await drafts.update_draft(ctx, uid="3", mailbox="Drafts", to="a@example.se",
                                           subject="Ny", body="b", bcc="h@example.se")
        msg = _parse(seen["raw"])
        app.imap.get_message.assert_awaited_once_with("Drafts", "3")
        assert seen["old_uid"] == "3"
        assert msg["Subject"] == "Ny" and msg["Bcc"] == "h@example.se"
        assert result == {"uid": "9", "mailbox": "Drafts",
                          "message_id": msg["Message-ID"], "replaced_uid": "3",
                          "replaced_moved_to": "Trash", "kept_headers": [],
                          "kept_attachments": []}

    def test_mcp_schema_requires_drafts_mailbox(self):
        from protonmail_mcp.server import mcp

        tool = mcp._tool_manager.get_tool("update_draft")
        schema = tool.parameters["properties"]["mailbox"]
        assert schema.get("const") == "Drafts" or schema.get("enum") == ["Drafts"]
        assert "mailbox" in tool.parameters["required"]


class TestSendDraft:
    @pytest.mark.asyncio
    async def test_only_drafts_mailbox(self):
        ctx, app = _ctx()
        app.imap.get_message = AsyncMock()
        with pytest.raises(ValueError, match="Bara utkast i Drafts"):
            await drafts.send_draft(ctx, uid="3", mailbox="INBOX")
        app.imap.get_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_reads_drafts_and_deletes_permanently_after_send(self):
        ctx, app = _ctx()
        app.imap.get_message = AsyncMock(return_value=(
            b"From: me@proton.me\r\nTo: a@example.se\r\nSubject: s\r\n"
            b"Message-ID: <d@proton.me>\r\n\r\nText\r\n"
        ))
        app.imap.delete_message = AsyncMock(return_value=True)
        app.smtp.send_prepared_message = AsyncMock(return_value=True)
        result = await drafts.send_draft(ctx, uid="3", mailbox="Drafts")
        app.imap.get_message.assert_awaited_once_with("Drafts", "3")
        app.imap.delete_message.assert_awaited_once_with("Drafts", "3", permanent=True)
        assert result == {"sent": True, "message_id": "<d@proton.me>", "draft_deleted": True}

    @pytest.mark.asyncio
    async def test_failed_send_keeps_draft(self):
        ctx, app = _ctx()
        app.imap.get_message = AsyncMock(return_value=b"To: a@example.se\r\n\r\nx\r\n")
        app.imap.delete_message = AsyncMock()
        app.smtp.send_prepared_message = AsyncMock(side_effect=OSError("nere"))
        with pytest.raises(OSError):
            await drafts.send_draft(ctx, uid="3", mailbox="Drafts")
        app.imap.delete_message.assert_not_called()

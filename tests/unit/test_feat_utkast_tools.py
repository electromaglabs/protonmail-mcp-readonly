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

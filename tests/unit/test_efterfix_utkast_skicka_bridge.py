"""Enhetstester: send_draft räknar med att Bridge själv tar bort skickade utkast (K2)."""
import email
import email.policy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp import imap_drafts
from protonmail_mcp.tools import drafts
from tests.feat_utkast_bridge import make_imap
from tests.fix_svar_support import make_client

RAW = b"From: me@proton.me\r\nTo: a@example.se\r\nSubject: s\r\n\r\nText\r\n"


class TestRemoveSentDraft:
    @pytest.mark.asyncio
    async def test_draft_already_gone_counts_as_removed_without_store(self):
        imap, bridge = make_imap()
        assert await imap_drafts.remove_sent_draft(imap, "4") is False
        assert not {"UID STORE", "UID EXPUNGE"} & set(bridge.names())

    @pytest.mark.asyncio
    async def test_draft_still_there_is_deleted_permanently(self):
        imap, bridge = make_imap()
        uid = bridge.add("Drafts", RAW, ("\\Draft",))
        assert await imap_drafts.remove_sent_draft(imap, uid) is True
        assert bridge.messages("Drafts") == {}
        assert ("UID EXPUNGE", uid) in bridge.commands

    @pytest.mark.asyncio
    async def test_refused_expunge_after_bridge_removed_it_is_not_an_error(self):
        imap, bridge = make_imap()
        uid = bridge.add("Drafts", RAW, ("\\Draft",))
        inner = bridge.client.uid.side_effect

        async def uid_cmd(command, *args):
            if command.upper() == "EXPUNGE":
                bridge.messages("Drafts").pop(int(uid), None)
                return SimpleNamespace(result="NO", lines=[b"gone"])
            return await inner(command, *args)

        bridge.client.uid.side_effect = uid_cmd
        assert await imap_drafts.remove_sent_draft(imap, uid) is False

    @pytest.mark.asyncio
    async def test_refused_expunge_with_draft_left_raises(self):
        imap, bridge = make_imap()
        uid = bridge.add("Drafts", RAW, ("\\Draft",))
        bridge.refuse["EXPUNGE"] = "nope"
        with pytest.raises(ValueError, match="permanenta raderingen"):
            await imap_drafts.remove_sent_draft(imap, uid)
        assert int(uid) in bridge.messages("Drafts")

    @pytest.mark.asyncio
    async def test_invalid_uid_is_rejected(self):
        imap, bridge = make_imap()
        with pytest.raises(ValueError, match="Ogiltigt UID"):
            await imap_drafts.remove_sent_draft(imap, "1:*")
        assert bridge.commands == []


def _ctx(raw: bytes):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.smtp = make_client("me@proton.me")
    app.smtp.send_prepared_message = AsyncMock(return_value=True)
    app.imap = MagicMock()
    app.imap.get_message = AsyncMock(return_value=raw)
    return ctx


PROTON_DRAFT = (
    b"From: me@proton.me\r\nTo: a@example.se\r\nSubject: s\r\n"
    b"X-Pm-Internal-Id: abc==\r\n"
    b"References: <p@example.se> <abc==@protonmail.internalid>\r\n\r\nText\r\n"
)


class TestSendDraftAfterSend:
    @pytest.mark.asyncio
    async def test_removed_by_bridge_gives_no_warning(self, monkeypatch):
        monkeypatch.setattr(drafts.imap_drafts, "remove_sent_draft", AsyncMock(return_value=False))
        result = await drafts.send_draft(_ctx(RAW), uid="3", mailbox="Drafts")
        assert result["draft_deleted"] is True and "warning" not in result

    @pytest.mark.asyncio
    async def test_failed_delete_of_draft_bridge_deletes_itself_gives_note(self, monkeypatch):
        monkeypatch.setattr(drafts.imap_drafts, "remove_sent_draft",
                            AsyncMock(side_effect=ValueError("NO")))
        result = await drafts.send_draft(_ctx(PROTON_DRAFT), uid="3", mailbox="Drafts")
        assert result["draft_deleted"] is True
        assert "warning" not in result
        assert "Bridge" in result["note"]

    @pytest.mark.asyncio
    async def test_failed_delete_of_other_draft_still_warns(self, monkeypatch):
        # Bara utkastets EGET interna id får Bridge att ta bort det
        raw = PROTON_DRAFT.replace(b"<abc==@protonmail.internalid>", b"<annat@protonmail.internalid>")
        monkeypatch.setattr(drafts.imap_drafts, "remove_sent_draft",
                            AsyncMock(side_effect=ValueError("NO")))
        result = await drafts.send_draft(_ctx(raw), uid="3", mailbox="Drafts")
        assert result["draft_deleted"] is False
        assert "Skicka inte igen" in result["warning"]

    @pytest.mark.asyncio
    async def test_failed_send_does_not_touch_draft(self, monkeypatch):
        remove = AsyncMock()
        monkeypatch.setattr(drafts.imap_drafts, "remove_sent_draft", remove)
        ctx = _ctx(RAW)
        ctx.request_context.lifespan_context.smtp.send_prepared_message = AsyncMock(
            side_effect=OSError("nere"))
        with pytest.raises(OSError):
            await drafts.send_draft(ctx, uid="3", mailbox="Drafts")
        remove.assert_not_called()

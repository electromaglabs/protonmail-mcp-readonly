"""Enhetstester för imap_drafts (feat-utkast): APPEND till Drafts och ersättning."""
import asyncio

import pytest

from protonmail_mcp import imap_drafts
from tests.feat_utkast_bridge import make_imap

RAW = (
    b"From: me@proton.me\r\nTo: a@example.se\r\nSubject: Hej\r\n"
    b"Message-ID: <abc@proton.me>\r\n\r\nText\r\n"
)


class TestAppendDraft:
    @pytest.mark.asyncio
    async def test_appends_to_quoted_drafts_with_draft_and_seen_flags(self):
        imap, bridge = make_imap()
        await imap_drafts.append_draft(imap, RAW, "<abc@proton.me>")
        assert ("APPEND", "Drafts", r"(\Draft \Seen)") in bridge.commands
        call = bridge.client.append.call_args
        assert call.kwargs["mailbox"] == '"Drafts"'
        assert bytes(call.args[0]) == RAW

    @pytest.mark.asyncio
    async def test_returns_uid_from_appenduid(self):
        imap, bridge = make_imap()
        bridge.add("Drafts", b"Subject: annat\r\n\r\nx\r\n")
        uid = await imap_drafts.append_draft(imap, RAW, "<abc@proton.me>")
        assert uid == "2"
        # Inget extra sökande behövs när APPENDUID finns
        assert "SEARCH" not in bridge.names()

    @pytest.mark.asyncio
    async def test_falls_back_to_message_id_search(self):
        imap, bridge = make_imap()
        bridge.appenduid = False
        bridge.add("Drafts", b"Message-ID: <other@proton.me>\r\n\r\nx\r\n")
        uid = await imap_drafts.append_draft(imap, RAW, "<abc@proton.me>")
        assert uid == "2"
        search = [c for c in bridge.commands if c[0] == "SEARCH"]
        assert 'HEADER Message-ID "<abc@proton.me>"' in search[0][1]

    @pytest.mark.asyncio
    async def test_fallback_without_hit_gives_none(self):
        imap, bridge = make_imap()
        bridge.appenduid = False
        uid = await imap_drafts.append_draft(imap, RAW, "<finns-inte@proton.me>")
        assert uid is None

    @pytest.mark.asyncio
    async def test_failed_fallback_search_does_not_hide_the_saved_draft(self):
        # Utkastet är redan sparat: ett sökfel får inte se ut som att det misslyckades
        imap, bridge = make_imap()
        bridge.appenduid = False
        bridge.refuse["SEARCH"] = "search failed"
        uid = await imap_drafts.append_draft(imap, RAW, "<abc@proton.me>")
        assert uid is None
        assert len(bridge.messages("Drafts")) == 1

    @pytest.mark.asyncio
    async def test_refused_append_raises(self):
        imap, bridge = make_imap()
        bridge.refuse["APPEND"] = "quota exceeded"
        with pytest.raises(ValueError, match="Sparandet av utkastet i Drafts misslyckades.*quota"):
            await imap_drafts.append_draft(imap, RAW, "<abc@proton.me>")

    @pytest.mark.asyncio
    async def test_append_times_out(self):
        imap, bridge = make_imap()
        imap.uid_timeout = 0.01

        async def hang(*_a, **_k):
            await asyncio.sleep(1)

        bridge.client.append.side_effect = hang
        with pytest.raises(asyncio.TimeoutError, match="APPEND"):
            await imap_drafts.append_draft(imap, RAW, "<abc@proton.me>")
        # Anslutningen är i okänt läge efter en timeout och släpps
        assert imap._client is None

    @pytest.mark.asyncio
    async def test_message_id_with_control_chars_is_never_searched(self):
        imap, bridge = make_imap()
        bridge.appenduid = False
        uid = await imap_drafts.append_draft(imap, RAW, "<a\r\nX DELETE INBOX>")
        assert uid is None
        assert "SEARCH" not in bridge.names()


class TestReplaceDraft:
    @pytest.mark.asyncio
    async def test_checks_old_then_appends_then_moves_only_the_old_uid_to_trash(self):
        # efterfix-utkast: det gamla utkastet flyttas till Trash i stället för att raderas
        imap, bridge = make_imap()
        old = bridge.add("Drafts", b"Subject: gammal\r\n\r\nx\r\n", ("\\Draft",))
        new_uid = await imap_drafts.replace_draft(imap, old, RAW, "<abc@proton.me>")
        assert new_uid == "2"
        assert list(bridge.messages("Drafts")) == [2]
        names = bridge.names()
        assert names.index("APPEND") < names.index("UID MOVE")
        assert ("UID MOVE", old, '"Trash"') in bridge.commands
        assert not {"UID STORE", "UID EXPUNGE", "EXPUNGE"} & set(names)

    @pytest.mark.asyncio
    async def test_invalid_uid_is_rejected_before_anything_is_sent(self):
        imap, bridge = make_imap()
        with pytest.raises(ValueError, match="Ogiltigt UID"):
            await imap_drafts.replace_draft(imap, "1:*", RAW, "<abc@proton.me>")
        assert bridge.commands == []

    @pytest.mark.asyncio
    async def test_missing_old_draft_appends_nothing(self):
        imap, bridge = make_imap()
        with pytest.raises(ValueError, match="Inget meddelande med UID 5 i Drafts"):
            await imap_drafts.replace_draft(imap, "5", RAW, "<abc@proton.me>")
        assert "APPEND" not in bridge.names()

    @pytest.mark.asyncio
    async def test_failed_append_leaves_old_draft_untouched(self):
        imap, bridge = make_imap()
        old = bridge.add("Drafts", b"Subject: gammal\r\n\r\nx\r\n")
        bridge.refuse["APPEND"] = "nope"
        with pytest.raises(ValueError, match="Sparandet av utkastet"):
            await imap_drafts.replace_draft(imap, old, RAW, "<abc@proton.me>")
        assert list(bridge.messages("Drafts")) == [int(old)]
        assert not {"UID STORE", "UID EXPUNGE"} & set(bridge.names())

    @pytest.mark.asyncio
    async def test_failed_move_reports_both_uids(self):
        imap, bridge = make_imap()
        old = bridge.add("Drafts", b"Subject: gammal\r\n\r\nx\r\n")
        bridge.refuse["MOVE"] = "move failed"
        with pytest.raises(ValueError) as excinfo:
            await imap_drafts.replace_draft(imap, old, RAW, "<abc@proton.me>")
        text = str(excinfo.value)
        assert "UID 2" in text and f"UID {old}" in text
        # Det gamla utkastet ligger kvar orört
        assert int(old) in bridge.messages("Drafts")

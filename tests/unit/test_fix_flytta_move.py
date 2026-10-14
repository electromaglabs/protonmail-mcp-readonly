"""IMAPClient.move_message: UID MOVE, vakter mot Bridge-fällor och kontrollerade svar."""
import pytest

from tests.fix_flytta_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


WRITES = {"UID MOVE", "UID COPY", "UID STORE", "UID EXPUNGE", "EXPUNGE"}


def _writes(bridge):
    return [c for c in bridge.commands if c[0] in WRITES]


class TestMoveUsesUidMove:
    async def test_moves_only_that_uid_with_uid_move(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("INBOX", "42")
        assert await imap.move_message("INBOX", "42", "Archive") is True
        assert _writes(bridge) == [("UID MOVE", "42", '"Archive"')]

    async def test_never_expunges_whole_mailbox(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("INBOX", "42")
        await imap.move_message("INBOX", "42", "Folders/Projekt")
        assert bridge.sent("EXPUNGE") == []

    async def test_label_target_uses_uid_move(self, imap_and_bridge):
        # Bridge behåller mejlet i INBOX när målet för MOVE är en etikett
        imap, bridge = imap_and_bridge
        bridge.add("INBOX", "42")
        await imap.move_message("INBOX", "42", "Labels/Kvitton")
        assert _writes(bridge) == [("UID MOVE", "42", '"Labels/Kvitton"')]

    async def test_target_name_is_encoded(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("INBOX", "42")
        await imap.move_message("INBOX", "42", "Folders/Näs")
        assert _writes(bridge) == [("UID MOVE", "42", '"Folders/N&AOQ-s"')]


class TestMoveGuards:
    @pytest.mark.parametrize("source,target", [
        ("Trash", "Trash"), ("Drafts", "Drafts"), ("INBOX", "INBOX"),
        ("inbox", "INBOX"), ("Folders/A", "Folders/A"),
    ])
    async def test_rejects_same_source_and_target(self, imap_and_bridge, source, target):
        imap, bridge = imap_and_bridge
        bridge.add(source, "7")
        with pytest.raises(ValueError, match="samma mapp"):
            await imap.move_message(source, "7", target)
        assert _writes(bridge) == []

    @pytest.mark.parametrize("source", ["Starred", "Labels/X"])
    @pytest.mark.parametrize("target", ["Trash", "Drafts"])
    async def test_rejects_trash_or_drafts_from_label_view(self, imap_and_bridge, source, target):
        # Mejlet kan redan ligga i målet; då raderar Bridge det permanent (N1)
        imap, bridge = imap_and_bridge
        bridge.add(source, "7")
        with pytest.raises(ValueError, match=f"redan ligga i {target}"):
            await imap.move_message(source, "7", target)
        assert _writes(bridge) == []

    @pytest.mark.parametrize("source,target", [("All Mail", "Archive"), ("INBOX", "All Mail")])
    async def test_rejects_all_mail(self, imap_and_bridge, source, target):
        imap, bridge = imap_and_bridge
        bridge.add(source, "7")
        with pytest.raises(ValueError, match="All Mail"):
            await imap.move_message(source, "7", target)
        assert _writes(bridge) == []

    @pytest.mark.parametrize("source,target", [("INBOX", "Sent"), ("Sent", "INBOX")])
    async def test_rejects_inbox_sent(self, imap_and_bridge, source, target):
        imap, bridge = imap_and_bridge
        bridge.add(source, "7")
        with pytest.raises(ValueError, match="INBOX och Sent"):
            await imap.move_message(source, "7", target)
        assert _writes(bridge) == []

    async def test_guard_runs_before_contacting_bridge(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        with pytest.raises(ValueError):
            await imap.move_message("Trash", "7", "Trash")
        assert bridge.commands == []


class TestMoveChecksResults:
    async def test_unknown_uid_raises(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        with pytest.raises(ValueError, match="Inget meddelande med UID 99999 i INBOX"):
            await imap.move_message("INBOX", "99999", "Archive")
        assert _writes(bridge) == []

    async def test_uid_existence_is_checked_with_uid_fetch(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("INBOX", "42")
        await imap.move_message("INBOX", "42", "Archive")
        assert bridge.sent("UID FETCH") == [("UID FETCH", "42", "(UID)")]

    async def test_other_uid_in_fetch_answer_is_not_a_match(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("INBOX", "420")

        async def fetch_other(command, *args):
            bridge.commands.append((f"UID {command.upper()}", *args))
            from types import SimpleNamespace
            return SimpleNamespace(result="OK", lines=[b"1 FETCH (UID 420)", b"done"])
        bridge.client.uid.side_effect = fetch_other
        with pytest.raises(ValueError, match="Inget meddelande med UID 42 "):
            await imap.move_message("INBOX", "42", "Archive")

    async def test_move_no_raises_with_server_text(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("INBOX", "42")
        bridge.refuse["MOVE"] = "operation not allowed"
        with pytest.raises(ValueError, match="operation not allowed"):
            await imap.move_message("INBOX", "42", "Archive")

    async def test_fetch_no_raises(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("INBOX", "42")
        bridge.refuse["FETCH"] = "backend error"
        with pytest.raises(ValueError, match="backend error"):
            await imap.move_message("INBOX", "42", "Archive")
        assert _writes(bridge) == []

    async def test_rejects_invalid_uid(self, imap_and_bridge):
        imap, _ = imap_and_bridge
        with pytest.raises(ValueError, match="Ogiltigt UID"):
            await imap.move_message("INBOX", "1:*", "Archive")

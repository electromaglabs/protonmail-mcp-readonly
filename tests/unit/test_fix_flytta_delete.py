"""IMAPClient.delete_message: flytt till Trash som standard, permanent radering bara uttryckligen."""
from types import SimpleNamespace

import pytest

from tests.fix_flytta_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


WRITES = {"UID MOVE", "UID COPY", "UID STORE", "UID EXPUNGE", "EXPUNGE"}


def _writes(bridge):
    return [c for c in bridge.commands if c[0] in WRITES]


class TestDeleteMovesToTrash:
    @pytest.mark.parametrize("mailbox", ["INBOX", "Archive", "Sent", "Spam", "Folders/Projekt", "Drafts"])
    async def test_moves_to_trash(self, imap_and_bridge, mailbox):
        imap, bridge = imap_and_bridge
        bridge.add(mailbox, "42")
        assert await imap.delete_message(mailbox, "42") is True
        assert _writes(bridge) == [("UID MOVE", "42", '"Trash"')]

    async def test_already_in_trash_requires_permanent(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("Trash", "7")
        with pytest.raises(ValueError, match="permanent=True"):
            await imap.delete_message("Trash", "7")
        assert _writes(bridge) == []

    @pytest.mark.parametrize("mailbox", ["Starred", "Labels/X"])
    async def test_rejects_label_view(self, imap_and_bridge, mailbox):
        imap, bridge = imap_and_bridge
        bridge.add(mailbox, "7")
        with pytest.raises(ValueError, match="redan ligga i Trash"):
            await imap.delete_message(mailbox, "7")
        assert _writes(bridge) == []

    async def test_rejects_all_mail(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("All Mail", "7")
        with pytest.raises(ValueError, match="All Mail"):
            await imap.delete_message("All Mail", "7")
        assert _writes(bridge) == []

    async def test_unknown_uid_raises(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        with pytest.raises(ValueError, match="Inget meddelande med UID 99999 i INBOX"):
            await imap.delete_message("INBOX", "99999")
        assert _writes(bridge) == []

    async def test_move_no_raises(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("INBOX", "42")
        bridge.refuse["MOVE"] = "backend error"
        with pytest.raises(ValueError, match="backend error"):
            await imap.delete_message("INBOX", "42")


class TestPermanentDelete:
    @pytest.mark.parametrize("mailbox", ["Trash", "Drafts"])
    async def test_store_then_uid_expunge(self, imap_and_bridge, mailbox):
        imap, bridge = imap_and_bridge
        bridge.add(mailbox, "7")
        assert await imap.delete_message(mailbox, "7", permanent=True) is True
        assert _writes(bridge) == [
            ("UID STORE", "7", "+FLAGS", r"(\Deleted)"),
            ("UID EXPUNGE", "7"),
        ]

    @pytest.mark.parametrize("mailbox", ["INBOX", "Archive", "Labels/X", "Starred", "All Mail"])
    async def test_rejected_outside_trash_and_drafts(self, imap_and_bridge, mailbox):
        imap, bridge = imap_and_bridge
        bridge.add(mailbox, "7")
        with pytest.raises(ValueError, match="bara i Trash"):
            await imap.delete_message(mailbox, "7", permanent=True)
        assert bridge.commands == []

    async def test_unknown_uid_raises(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        with pytest.raises(ValueError, match="Inget meddelande med UID 5 i Trash"):
            await imap.delete_message("Trash", "5", permanent=True)
        assert _writes(bridge) == []

    async def test_store_no_raises_without_expunge(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("Trash", "7")
        bridge.refuse["STORE"] = "store failed"
        with pytest.raises(ValueError, match="store failed"):
            await imap.delete_message("Trash", "7", permanent=True)
        assert bridge.sent("UID EXPUNGE") == []

    async def test_expunge_no_restores_flag_and_raises(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("Trash", "7")
        bridge.refuse["EXPUNGE"] = "operation not allowed"
        with pytest.raises(ValueError, match="operation not allowed"):
            await imap.delete_message("Trash", "7", permanent=True)
        assert bridge.sent("UID STORE")[-1] == ("UID STORE", "7", "-FLAGS", r"(\Deleted)")

    async def test_never_plain_expunge(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add("Trash", "7")
        await imap.delete_message("Trash", "7", permanent=True)
        assert bridge.sent("EXPUNGE") == []


async def test_rejects_invalid_uid(monkeypatch):
    imap, _ = make_client(monkeypatch)
    with pytest.raises(ValueError, match="Ogiltigt UID"):
        await imap.delete_message("INBOX", "1:*")

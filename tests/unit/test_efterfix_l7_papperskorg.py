"""L7: flytt till Trash/Drafts av ett mejl som redan ligger där raderar det permanent hos Bridge.

Ett mejl till sig själv är ETT Proton-mejl i både INBOX och Sent. Bridges
Sent-vy visar det i 20–40 s efter att INBOX-kopian flyttats till Trash, och
UID MOVE till Trash under den tiden ger NO Code=2501 — men mejlet är då
raderat permanent. Verktygen ska känna igen läget via Message-ID (samma tid och
storlek) och då inte skicka något till Bridge för det UID:t.
"""
import pytest

from protonmail_mcp import imap_bulk
from tests.efterfix_l7_bridge import make_client

SELF = "<sjalv@x>"


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


def _note_to_self(bridge, mid=SELF, inbox="10", sent="20"):
    bridge.put("INBOX", inbox, mid)
    bridge.put("Sent", sent, mid)
    bridge.put("All Mail", str(1000 + int(sent)), mid)


def _commands_in(bridge, mailbox, names):
    selected, out = None, []
    for cmd in bridge.commands:
        if cmd[0] == "SELECT":
            selected = cmd[1]
        elif cmd[0] in names and selected == mailbox:
            out.append(cmd)
    return out


class TestSingleUid:
    async def test_delete_of_sent_copy_after_inbox_copy_keeps_the_mail(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _note_to_self(bridge)
        assert await imap.delete_message("INBOX", "10") is True
        res = await imap.delete_message("Sent", "20")
        assert res["ok"] == ["20"] and res["failed"] == []
        assert "ligger redan i papperskorgen" in res["note"]
        assert "40 s" in res["note"]
        assert SELF not in bridge.permanently_deleted
        assert "Trash" in bridge.views_of(SELF)
        assert _commands_in(bridge, "Sent", {"UID MOVE", "UID COPY"}) == []

    async def test_move_to_trash_of_sent_copy_keeps_the_mail(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _note_to_self(bridge)
        await imap.delete_message("INBOX", "10")
        res = await imap.move_message("Sent", "20", "Trash")
        assert res["ok"] == ["20"]
        assert SELF not in bridge.permanently_deleted

    async def test_move_to_drafts_of_mail_already_in_drafts(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Folders/X")
        bridge.put("Drafts", "3", "<utkast@x>")
        bridge.put("Folders/X", "4", "<utkast@x>")
        res = await imap.move_message("Folders/X", "4", "Drafts")
        assert res["ok"] == ["4"]
        assert "ligger redan i Drafts" in res["note"]
        assert "<utkast@x>" not in bridge.permanently_deleted

    async def test_other_mail_with_same_message_id_is_moved(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        # Ett annat mejl (annan storlek) med samma Message-ID ligger redan i Trash
        bridge.put("Trash", "5", SELF)
        bridge.put_twin("Sent", "20", SELF, size=4321)
        assert await imap.delete_message("Sent", "20") is True
        assert ("UID MOVE", "20", '"Trash"') in bridge.writes()

    async def test_mail_without_message_id_is_moved_without_search(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_without_message_id("INBOX", "30")
        assert await imap.delete_message("INBOX", "30") is True
        assert ("SELECT", "Trash") not in bridge.commands
        assert bridge.sent("SEARCH") == []
        assert bridge.writes() == [("UID MOVE", "30", '"Trash"')]

    async def test_move_to_ordinary_folder_is_not_checked(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put("INBOX", "10", SELF)
        assert await imap.move_message("INBOX", "10", "Archive") is True
        assert bridge.sent("SEARCH") == []
        assert ("SELECT", "Archive") not in bridge.commands

    async def test_failed_check_writes_nothing(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put("INBOX", "10", SELF)
        bridge.refuse["SEARCH"] = "backend error"
        with pytest.raises(ValueError, match="backend error"):
            await imap.delete_message("INBOX", "10")
        assert bridge.writes() == []

    async def test_draft_replacement_still_moves_old_draft(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put("Drafts", "7", "<v1@x>")
        assert await imap._move("Drafts", "7", "Trash") is True
        assert "Trash" in bridge.views_of("<v1@x>")


class TestBulk:
    async def test_bulk_delete_skips_mail_already_in_trash(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _note_to_self(bridge)
        bridge.put("Sent", "21", "<annat@x>", size=2000)
        await imap.delete_message("INBOX", "10")
        bridge.commands.clear()
        res = await imap_bulk.delete(imap, "Sent", ["20", "21"])
        assert res["ok"] == ["20", "21"] and res["failed"] == []
        assert "UID 20" in res["note"] and "21" not in res["note"]
        assert SELF not in bridge.permanently_deleted
        assert "Trash" in bridge.views_of("<annat@x>")
        assert bridge.writes() == [("UID MOVE", "21", '"Trash"')]

    async def test_bulk_move_to_trash_skips_mail_already_in_trash(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _note_to_self(bridge)
        await imap.delete_message("INBOX", "10")
        res = await imap_bulk.move(imap, "Sent", ["20"], "Trash")
        assert res["ok"] == ["20"] and "note" in res
        assert SELF not in bridge.permanently_deleted

    async def test_all_skipped_sends_no_move(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _note_to_self(bridge, "<a@x>", "10", "20")
        _note_to_self(bridge, "<b@x>", "11", "21")
        await imap_bulk.delete(imap, "INBOX", ["10", "11"])
        bridge.commands.clear()
        res = await imap_bulk.delete(imap, "Sent", ["20", "21"])
        assert res["ok"] == ["20", "21"]
        assert "UID 20, 21" in res["note"]
        assert bridge.writes() == []

    async def test_one_search_per_call_not_per_uid(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        uids = [str(100 + i) for i in range(5)]
        for uid in uids:
            bridge.put("Sent", uid, f"<m{uid}@x>")
        res = await imap_bulk.delete(imap, "Sent", uids)
        assert res == {"ok": uids, "failed": []}
        assert len(_commands_in(bridge, "Trash", {"SEARCH"})) == 1

    async def test_large_batch_searches_in_chunks(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        uids = [str(100 + i) for i in range(45)]
        for uid in uids:
            bridge.put("Sent", uid, f"<m{uid}@x>")
        res = await imap_bulk.delete(imap, "Sent", uids)
        assert res["ok"] == uids
        assert len(_commands_in(bridge, "Trash", {"SEARCH"})) == 3

    async def test_missing_uid_still_reported_as_failed(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _note_to_self(bridge)
        await imap.delete_message("INBOX", "10")
        res = await imap_bulk.delete(imap, "Sent", ["20", "99"])
        assert res["ok"] == ["20"]
        assert [f["uid"] for f in res["failed"]] == ["99"]

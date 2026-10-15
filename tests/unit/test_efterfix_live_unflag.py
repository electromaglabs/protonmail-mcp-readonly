"""L1: unflag_email tar bort mejlet ur Starred-vyn direkt, inte först vid Bridges nästa händelse.

Live: -FLAGS \\Flagged tog bort stjärnan i Proton (Bridge anropar UnlabelMessages
med Starred), men Bridges Starred-vy uppdateras först när händelsen hämtas
(var 20:e–40:e sekund), så mejlet låg kvar i Starred med FLAGS ().
"""
import pytest

from protonmail_mcp import imap_labels
from tests.efterfix_live_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


def _starred(bridge, mid, inbox_uid="1", starred_uid="7"):
    bridge.put_mail("INBOX", inbox_uid, mid, flags=("\\Flagged",))
    bridge.put("Starred", starred_uid, mid)


class TestUnflagRemovesFromStarredView:
    async def test_unflag_from_inbox_removes_from_starred_view(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _starred(bridge, "<a@x>")
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res == {"ok": ["1"], "failed": []}
        assert bridge.messages["<a@x>"]["flags"] == set()
        assert bridge.views_of("<a@x>") == ["INBOX"]
        # Bara Starred-UID:t expungeras, aldrig utan UID
        assert ("UID EXPUNGE", "7") in bridge.writes()
        assert not bridge.sent("EXPUNGE")

    async def test_unflag_in_starred_view_removes_it_there(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _starred(bridge, "<a@x>")
        res = await imap_labels.set_starred(imap, "Starred", ["7"], False)
        assert res == {"ok": ["7"], "failed": []}
        assert bridge.views_of("<a@x>") == ["INBOX"]
        assert bridge.messages["<a@x>"]["flags"] == set()

    async def test_only_the_unflagged_message_leaves_starred(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _starred(bridge, "<a@x>", "1", "7")
        _starred(bridge, "<b@x>", "2", "8")
        await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert bridge.views_of("<b@x>") == ["INBOX", "Starred"]
        assert bridge.messages["<b@x>"]["flags"] == {"\\Flagged"}

    async def test_not_in_starred_view_is_fine(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<a@x>", flags=("\\Flagged",))
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res == {"ok": ["1"], "failed": []}
        assert not bridge.sent("UID EXPUNGE")

    async def test_starred_view_cleanup_refused_still_ok(self, imap_and_bridge):
        """Stjärnan är borta i Proton när STORE lyckats; vyn är bara en eftersläpning."""
        imap, bridge = imap_and_bridge
        _starred(bridge, "<a@x>")
        bridge.refuse["EXPUNGE"] = "backend error"
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res["ok"] == ["1"] and res["failed"] == []
        # G5K-5: att vyn inte gick att städa nämns i svaret, men är inget fel
        assert "Starred" in res["note"]
        assert bridge.messages["<a@x>"]["flags"] == set()
        # \Deleted lämnas inte kvar i Starred
        assert ("Starred", "7") not in bridge.deleted

    async def test_store_refused_does_not_touch_starred(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _starred(bridge, "<a@x>")
        bridge.refuse["STORE"] = "backend error"
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res["ok"] == []
        assert bridge.views_of("<a@x>") == ["INBOX", "Starred"]
        assert not bridge.sent("UID EXPUNGE")

    async def test_flagging_does_not_expunge(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<a@x>")
        await imap_labels.set_starred(imap, "INBOX", ["1"], True)
        assert not bridge.sent("UID EXPUNGE")

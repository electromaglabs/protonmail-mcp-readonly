"""G5K-1/F1: permanent radering med Code=2501 räknar ett mejl som raderat först när det är borta ur All Mail.

Bridge (connector.go, removeMessagesFromMailboxWithUnlabelCallOnFolders):
UnlabelMessages(Trash) för hela omgången, och vid fel return före
DeleteMessage. Ett mejl som redan var raderat i Proton (fantomen) ger 2501;
alla andra mejl i omgången tappar Trash men raderas inte — de blir kvar i All
Mail utan mapp. Inget i koden gäller bara utkast.
"""
import pytest

from protonmail_mcp import imap_bulk, imap_client
from tests.efterfix_slut_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    monkeypatch.setattr(imap_client, "_GONE_TIMEOUT", 0.2)
    monkeypatch.setattr(imap_client, "_GONE_INTERVAL", 0.01)
    return make_client(monkeypatch)


def _phantom_and_regular(bridge):
    bridge.put_mail("Trash", "5", "<gone@x>", all_mail_uid="50")
    bridge.phantoms.add("<gone@x>")  # redan raderat i Proton, Trash-vyn visar det ännu
    bridge.put_mail("Trash", "6", "<keep@x>", all_mail_uid="51")  # vanligt mottaget mejl
    bridge.no_then_vanish["Trash"] = [1, 1]


class TestRegularMailInA2501Batch:
    async def test_regular_mail_left_in_all_mail_is_deleted_via_trash(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _phantom_and_regular(bridge)
        res = await imap_bulk.delete(imap, "Trash", ["5", "6"], permanent=True)
        assert res == {"ok": ["5", "6"], "failed": []}
        assert bridge.views_of("<keep@x>") == []
        assert ("UID COPY", "51", '"Trash"') in bridge.writes()
        assert not bridge.sent("EXPUNGE")

    async def test_without_internal_id_message_id_is_used(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.internal_ids = False
        _phantom_and_regular(bridge)
        res = await imap_bulk.delete(imap, "Trash", ["5", "6"], permanent=True)
        assert res == {"ok": ["5", "6"], "failed": []}
        assert bridge.views_of("<keep@x>") == []

    async def test_single_regular_mail(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "6", "<keep@x>", all_mail_uid="51")
        bridge.no_then_vanish["Trash"] = [1, 1]
        assert await imap.delete_message("Trash", "6", permanent=True) is True
        assert bridge.views_of("<keep@x>") == []

    async def test_phantom_alone_is_ok_without_writes_in_all_mail(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "5", "<gone@x>", all_mail_uid="50")
        bridge.phantoms.add("<gone@x>")
        bridge.no_then_vanish["Trash"] = [1, 1]
        res = await imap_bulk.delete(imap, "Trash", ["5"], permanent=True)
        assert res == {"ok": ["5"], "failed": []}
        assert not bridge.sent("UID COPY")
        # Kontrollen i All Mail gjordes
        assert ("SELECT", "All Mail") in bridge.commands

    async def test_labelled_regular_mail_keeps_its_label(self, imap_and_bridge):
        # Har mejlet en etikett raderar Bridge det inte, bara Trash tas bort —
        # som vid en lyckad permanent radering. Återställningen gör samma sak.
        imap, bridge = imap_and_bridge
        _phantom_and_regular(bridge)
        bridge.put("Labels/Kvitton", "3", "<keep@x>")
        res = await imap_bulk.delete(imap, "Trash", ["5", "6"], permanent=True)
        assert res["ok"] == ["5", "6"]
        assert "Trash" not in bridge.views_of("<keep@x>")


class TestCannotTellIsFailedNotOk:
    async def test_ambiguous_in_all_mail(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.internal_ids = False
        _phantom_and_regular(bridge)
        twin = bridge.put_twin("Archive", "3", "<keep@x>", all_mail_uid="52")
        res = await imap_bulk.delete(imap, "Trash", ["5", "6"], permanent=True)
        assert res["ok"] == ["5"]
        assert [f["uid"] for f in res["failed"]] == ["6"]
        assert "All Mail" in res["failed"][0]["error"]
        assert not bridge.sent("UID COPY")
        assert bridge.views_of(twin) == ["Archive", "All Mail"]

    async def test_search_in_all_mail_refused(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _phantom_and_regular(bridge)
        bridge.refuse["SEARCH"] = "SEARCH nekad"
        res = await imap_bulk.delete(imap, "Trash", ["5", "6"], permanent=True)
        assert res["ok"] == []
        assert [f["uid"] for f in res["failed"]] == ["5", "6"]
        assert all("All Mail" in f["error"] for f in res["failed"])

    async def test_mail_without_any_identity(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.internal_ids = False
        bridge.shown_message_id = lambda key: ""
        bridge.put_mail("Trash", "6", "<keep@x>", all_mail_uid="51")
        bridge.no_then_vanish["Trash"] = [1, 1]
        res = await imap_bulk.delete(imap, "Trash", ["6"], permanent=True)
        assert res["ok"] == []
        assert "All Mail" in res["failed"][0]["error"]

    async def test_single_raises_when_it_cannot_tell(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "6", "<keep@x>", all_mail_uid="51")
        bridge.no_then_vanish["Trash"] = [1, 1]
        bridge.refuse["SEARCH"] = "SEARCH nekad"
        with pytest.raises(ValueError, match="All Mail"):
            await imap.delete_message("Trash", "6", permanent=True)

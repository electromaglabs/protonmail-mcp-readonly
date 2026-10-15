"""L2/L3: permanent radering när Bridge svarar NO men ändå raderar.

Live: UID EXPUNGE i Trash gav "NO failed to unlabel messages: Message does not
exist (Code=2501)" för alla UID:n, men mejlen försvann ur Trash inom ~10 s
(nästa händelsehämtning). Ett utkast i samma omgång blev kvar i All Mail utan
mapp — föräldralöst, osynligt i Drafts och Trash.
"""
import pytest

from protonmail_mcp import imap_bulk, imap_client
from tests.efterfix_live_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    monkeypatch.setattr(imap_client, "_GONE_TIMEOUT", 0.2)
    monkeypatch.setattr(imap_client, "_GONE_INTERVAL", 0.01)
    return make_client(monkeypatch)


class TestNoButDeletedAnyway:
    async def test_bulk_reports_ok_when_messages_vanish(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "5", "<a@x>", all_mail_uid="50")
        bridge.put_mail("Trash", "6", "<b@x>", all_mail_uid="51")
        bridge.no_then_vanish["Trash"] = [2, 1]
        res = await imap_bulk.delete(imap, "Trash", ["5", "6"], permanent=True)
        assert res == {"ok": ["5", "6"], "failed": []}
        assert bridge.views_of("<a@x>") == []

    async def test_single_reports_true_when_message_vanishes(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "5", "<a@x>", all_mail_uid="50")
        bridge.no_then_vanish["Trash"] = [2, 1]
        assert await imap.delete_message("Trash", "5", permanent=True) is True

    async def test_still_there_after_waiting_is_failed(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "5", "<a@x>", all_mail_uid="50")
        bridge.no_then_vanish["Trash"] = [10**9, 1]
        res = await imap_bulk.delete(imap, "Trash", ["5"], permanent=True)
        assert res["ok"] == []
        assert "Code=2501" in res["failed"][0]["error"]
        assert "finns kvar" in res["failed"][0]["error"]
        # \Deleted lämnas inte kvar
        assert ("Trash", "5") not in bridge.deleted

    async def test_single_still_there_raises(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "5", "<a@x>", all_mail_uid="50")
        bridge.no_then_vanish["Trash"] = [10**9, 1]
        with pytest.raises(ValueError, match="Code=2501"):
            await imap.delete_message("Trash", "5", permanent=True)

    async def test_ok_path_does_not_wait_or_reselect(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "5", "<a@x>", all_mail_uid="50")
        res = await imap_bulk.delete(imap, "Trash", ["5"], permanent=True)
        assert res == {"ok": ["5"], "failed": []}
        assert [c for c in bridge.sent("SELECT")] == [("SELECT", "Trash")]


class TestOrphanedDraft:
    async def test_orphaned_draft_is_deleted_via_trash(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "5", "<a@x>", all_mail_uid="50")
        bridge.put_mail("Trash", "6", "<d@x>", draft=True, all_mail_uid="51")
        bridge.no_then_vanish["Trash"] = [1, 1]
        res = await imap_bulk.delete(imap, "Trash", ["5", "6"], permanent=True)
        assert res == {"ok": ["5", "6"], "failed": []}
        assert bridge.views_of("<d@x>") == []
        # Återställningen: COPY från All Mail till Trash, sedan permanent på just det UID:t
        assert ("UID COPY", "51", '"Trash"') in bridge.writes()
        assert not bridge.sent("EXPUNGE")

    async def test_single_orphaned_draft(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "6", "<d@x>", draft=True, all_mail_uid="51")
        bridge.no_then_vanish["Trash"] = [1, 1]
        assert await imap.delete_message("Trash", "6", permanent=True) is True
        assert bridge.views_of("<d@x>") == []

    async def test_orphan_recovery_refused_is_reported(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "6", "<d@x>", draft=True, all_mail_uid="51")
        bridge.no_then_vanish["Trash"] = [1, 2]
        res = await imap_bulk.delete(imap, "Trash", ["6"], permanent=True)
        assert res["ok"] == []
        error = res["failed"][0]["error"]
        assert "All Mail" in error and "utkast" in error.lower()

    async def test_draft_with_other_message_id_in_all_mail_is_left_alone(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "6", "<d@x>", draft=True, all_mail_uid="51")
        bridge.put_mail("Archive", "3", "<other@x>", all_mail_uid="52")
        bridge.no_then_vanish["Trash"] = [1, 1]
        await imap_bulk.delete(imap, "Trash", ["6"], permanent=True)
        assert bridge.views_of("<other@x>") == ["Archive", "All Mail"]
        assert ("UID COPY", "52", '"Trash"') not in bridge.writes()

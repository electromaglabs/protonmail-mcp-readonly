"""G5K-3: unflag_email får inte ta bort stjärnan från ett annat mejl.

Starred-vyn tas bort med UID EXPUNGE i Starred, vilket hos Bridge tar bort
stjärnan i Proton. Bara UID:n i Starred som är samma Proton-mejl
(X-Pm-Internal-Id) och som redan saknar \\Flagged får tas bort därifrån.
"""
import pytest

from protonmail_mcp import imap_labels
from tests.efterfix_slut_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


def _twin_starred(bridge):
    bridge.put_mail("INBOX", "1", "<a@x>", all_mail_uid="50")  # inte stjärnmärkt
    twin = bridge.put_twin("Archive", "3", "<a@x>", all_mail_uid="51", flags=("\\Flagged",))
    bridge.put("Starred", "7", twin)
    return twin


class TestTwinKeepsItsStar:
    async def test_with_internal_id(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        twin = _twin_starred(bridge)
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res["ok"] == ["1"]
        assert ("UID EXPUNGE", "7") not in bridge.writes()
        assert "Starred" in bridge.views_of(twin)
        assert "\\Flagged" in bridge.messages[twin]["flags"]

    async def test_without_internal_id(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.internal_ids = False
        twin = _twin_starred(bridge)
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res["ok"] == ["1"]
        assert ("UID EXPUNGE", "7") not in bridge.writes()
        assert "Starred" in bridge.views_of(twin)

    async def test_starred_uid_that_still_has_the_flag_is_left(self, imap_and_bridge):
        # Även med mailbox="Starred": ett UID som fortfarande har \Flagged
        # (t.ex. för att -FLAGS nekades för just det) tas inte bort ur vyn
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<a@x>", flags=("\\Flagged",))
        bridge.put("Starred", "7", "<a@x>")
        await imap_labels._leave_starred_view(imap, "Starred", ["7"])
        assert not bridge.sent("UID EXPUNGE")
        assert bridge.views_of("<a@x>") == ["INBOX", "Starred"]


class TestStillLeavesStarredView:
    @pytest.mark.parametrize("internal_ids", [True, False])
    async def test_unflagged_mail_leaves_starred(self, imap_and_bridge, internal_ids):
        imap, bridge = imap_and_bridge
        bridge.internal_ids = internal_ids
        bridge.put_mail("INBOX", "1", "<a@x>", flags=("\\Flagged",))
        bridge.put("Starred", "7", "<a@x>")
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res == {"ok": ["1"], "failed": []}
        assert bridge.views_of("<a@x>") == ["INBOX"]

    async def test_with_uid_from_starred(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<a@x>", flags=("\\Flagged",))
        bridge.put("Starred", "7", "<a@x>")
        res = await imap_labels.set_starred(imap, "Starred", ["7"], False)
        assert res == {"ok": ["7"], "failed": []}
        assert bridge.views_of("<a@x>") == ["INBOX"]

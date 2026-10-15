"""G5K-2: mejlets identitet är Protons X-Pm-Internal-Id, inte Message-ID + tid + storlek.

Live (läs-endast, 2026-10-15): två OLIKA Proton-mejl i Trash har samma
Message-ID, INTERNALDATE och RFC822.SIZE men olika X-Pm-Internal-Id. Alla mejl
i INBOX, Sent, Trash, Spam och All Mail har rubriken, och samma mejl har samma
värde i alla vyer.
"""
import pytest

from protonmail_mcp import imap_bulk, imap_labels
from tests.efterfix_slut_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


def _literal(headers: str) -> list:
    raw = headers.encode()
    return [
        b"1 FETCH (INTERNALDATE \"25-Mar-2025 13:31:04 +0000\" RFC822.SIZE 10 "
        b"BODY[HEADER.FIELDS (MESSAGE-ID X-PM-INTERNAL-ID)] {%d}" % len(raw),
        bytearray(raw),
        b" UID 7)",
    ]


class TestParseIdentities:
    def test_internal_id_is_parsed(self):
        out = imap_labels._parse_identities(_literal("Message-Id: <a@x>\r\nX-Pm-Internal-Id: abc_D-1==\r\n\r\n"))
        assert out["7"]["internal_id"] == "abc_D-1=="
        assert out["7"]["message_id"] == "<a@x>"

    def test_missing_internal_id_is_none(self):
        out = imap_labels._parse_identities(_literal("Message-Id: <a@x>\r\n\r\n"))
        assert out["7"]["internal_id"] is None

    def test_repeated_internal_id_is_not_trusted(self):
        out = imap_labels._parse_identities(
            _literal("X-Pm-Internal-Id: abc\r\nX-Pm-Internal-Id: def\r\nMessage-Id: <a@x>\r\n\r\n")
        )
        assert out["7"]["internal_id"] is None

    def test_internal_id_with_space_is_not_trusted(self):
        out = imap_labels._parse_identities(_literal("X-Pm-Internal-Id: a b\r\n\r\n"))
        assert out["7"]["internal_id"] is None

    def test_identity_fetch_asks_for_internal_id(self):
        assert "X-PM-INTERNAL-ID" in imap_labels._IDENTITY_ITEMS.upper()


class TestAlreadyInTarget:
    async def test_twin_in_trash_does_not_count_as_already_there(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<a@x>", all_mail_uid="50")
        bridge.put_twin("Trash", "9", "<a@x>", all_mail_uid="51")
        res = await imap_bulk.delete(imap, "INBOX", ["1"])
        assert res == {"ok": ["1"], "failed": []}
        assert bridge.views_of("<a@x>") == ["Trash", "All Mail"]

    async def test_single_delete_moves_despite_twin_in_trash(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<a@x>", all_mail_uid="50")
        bridge.put_twin("Trash", "9", "<a@x>", all_mail_uid="51")
        assert await imap.delete_message("INBOX", "1") is True
        assert bridge.views_of("<a@x>") == ["Trash", "All Mail"]

    async def test_same_proton_mail_in_trash_is_still_left_alone(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Sent", "1", "<a@x>", all_mail_uid="50")
        bridge.put("Trash", "9", "<a@x>")
        res = await imap_bulk.delete(imap, "Sent", ["1"])
        assert res["ok"] == ["1"] and "note" in res
        assert not bridge.writes()

    async def test_same_proton_mail_found_next_to_a_twin(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Sent", "1", "<a@x>", all_mail_uid="50")
        bridge.put("Trash", "9", "<a@x>")
        bridge.put_twin("Trash", "10", "<a@x>")
        res = await imap_bulk.delete(imap, "Sent", ["1"])
        assert res["ok"] == ["1"] and "note" in res
        assert not bridge.writes()

    async def test_searches_on_internal_id(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<a@x>")
        await imap_bulk.delete(imap, "INBOX", ["1"])
        searches = [c[1] for c in bridge.sent("SEARCH")]
        assert searches and all("X-Pm-Internal-Id" in s for s in searches)

    async def test_mail_without_message_id_is_checked_by_internal_id(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Sent", "1", "<a@x>")
        bridge.put("Trash", "9", "<a@x>")
        bridge.shown_message_id = lambda key: ""
        res = await imap_bulk.delete(imap, "Sent", ["1"])
        assert res["ok"] == ["1"] and "note" in res
        assert not bridge.writes()


class TestFallbackWithoutInternalId:
    async def test_ambiguous_twins_in_trash_fail_instead_of_ok(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.internal_ids = False
        bridge.put_mail("INBOX", "1", "<a@x>", all_mail_uid="50")
        bridge.put_twin("Trash", "9", "<a@x>")
        bridge.put_twin("Trash", "10", "<a@x>")
        res = await imap_bulk.delete(imap, "INBOX", ["1"])
        assert res["ok"] == []
        assert res["failed"][0]["uid"] == "1"
        assert "inte att avgöra" in res["failed"][0]["error"]
        assert "note" not in res
        assert not bridge.writes()
        assert bridge.views_of("<a@x>") == ["INBOX", "All Mail"]

    async def test_single_ambiguous_raises(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.internal_ids = False
        bridge.put_mail("INBOX", "1", "<a@x>")
        bridge.put_twin("Trash", "9", "<a@x>")
        bridge.put_twin("Trash", "10", "<a@x>")
        with pytest.raises(ValueError, match="inte att avgöra"):
            await imap.delete_message("INBOX", "1")
        assert not bridge.writes()

    async def test_one_legacy_match_is_still_left_alone(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.internal_ids = False
        bridge.put_mail("Sent", "1", "<a@x>")
        bridge.put("Trash", "9", "<a@x>")
        res = await imap_bulk.delete(imap, "Sent", ["1"])
        assert res["ok"] == ["1"] and "note" in res
        assert not bridge.writes()


class TestRemoveLabel:
    async def test_twin_with_same_label_is_not_ambiguous(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/Kvitton")
        bridge.put_mail("INBOX", "1", "<a@x>")
        bridge.put("Labels/Kvitton", "3", "<a@x>")
        twin = bridge.put_twin("INBOX", "2", "<a@x>")
        bridge.put("Labels/Kvitton", "4", twin)
        res = await imap_labels.remove_label(imap, "INBOX", ["1"], "Kvitton")
        assert res == {"ok": ["1"], "failed": []}
        assert bridge.views_of("<a@x>") == ["INBOX"]
        assert bridge.views_of(twin) == ["INBOX", "Labels/Kvitton"]

    async def test_without_internal_id_twins_stay_ambiguous(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.internal_ids = False
        bridge.add_label("Labels/Kvitton")
        bridge.put_mail("INBOX", "1", "<a@x>")
        bridge.put("Labels/Kvitton", "3", "<a@x>")
        twin = bridge.put_twin("INBOX", "2", "<a@x>")
        bridge.put("Labels/Kvitton", "4", twin)
        res = await imap_labels.remove_label(imap, "INBOX", ["1"], "Kvitton")
        assert res["ok"] == []
        assert "flera" in res["failed"][0]["error"]
        assert not bridge.sent("UID EXPUNGE")

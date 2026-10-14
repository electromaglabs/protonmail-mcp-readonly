"""imap_labels: add_label, remove_label och stjärnmärkning mot en låtsas-Bridge med etikettsemantik."""
import pytest

from protonmail_mcp import imap_labels
from protonmail_mcp.imap_labels import label_mailbox
from tests.feat_etiketter_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


class TestLabelName:
    @pytest.mark.parametrize("given,expected", [
        ("Kvitton", "Labels/Kvitton"),
        ("Labels/Kvitton", "Labels/Kvitton"),
        ("labels/Kvitton", "Labels/Kvitton"),
        ("  Kvitton ", "Labels/Kvitton"),
        ("Näs Samfällighet", "Labels/Näs Samfällighet"),
        ("Labels/neomeda\\/akassa", "Labels/neomeda\\/akassa"),
    ])
    def test_accepts_with_or_without_prefix(self, given, expected):
        assert label_mailbox(given) == expected

    @pytest.mark.parametrize("name", ["Starred", "starred", "Labels/Starred"])
    def test_starred_points_to_flag_email(self, name):
        with pytest.raises(ValueError, match="flag_email"):
            label_mailbox(name)

    @pytest.mark.parametrize("name", ["Folders/Projekt", "folders/x"])
    def test_folder_points_to_move_email(self, name):
        with pytest.raises(ValueError, match="move_email"):
            label_mailbox(name)

    @pytest.mark.parametrize("name", ["INBOX", "Trash", "All Mail", "archive"])
    def test_system_folder_is_no_label(self, name):
        with pytest.raises(ValueError, match="systemmapp"):
            label_mailbox(name)

    @pytest.mark.parametrize("name", ["", "   ", "Labels/", "Labels"])
    def test_empty_name(self, name):
        with pytest.raises(ValueError):
            label_mailbox(name)

    def test_sub_label_does_not_exist(self):
        with pytest.raises(ValueError, match="Underetiketter"):
            label_mailbox("A/B")

    def test_control_characters_rejected(self):
        with pytest.raises(ValueError):
            label_mailbox("X\r\nA1 DELETE INBOX")


class TestAddLabel:
    async def test_copies_only_existing_uids_in_one_command(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        for uid in ("1", "5"):
            bridge.put("INBOX", uid)
        result = await imap_labels.add_label(imap, "INBOX", ["1", "5", "9"], "K")
        assert result["ok"] == ["1", "5"]
        assert [f["uid"] for f in result["failed"]] == ["9"]
        assert bridge.writes() == [("UID COPY", "1,5", '"Labels/K"')]

    async def test_label_name_is_encoded(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/Näs")
        bridge.put("INBOX", "1")
        await imap_labels.add_label(imap, "INBOX", ["1"], "Näs")
        assert bridge.writes() == [("UID COPY", "1", '"Labels/N&AOQ-s"')]

    async def test_missing_label_refused_before_any_write(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put("INBOX", "1")
        with pytest.raises(ValueError, match=r'create_folder\("Labels/Ny"\)'):
            await imap_labels.add_label(imap, "INBOX", ["1"], "Ny")
        assert bridge.writes() == []

    async def test_list_refused_gives_error(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put("INBOX", "1")
        bridge.refuse["LIST"] = "backend down"
        with pytest.raises(ValueError, match="backend down"):
            await imap_labels.add_label(imap, "INBOX", ["1"], "K")
        assert bridge.writes() == []

    async def test_source_is_the_label_itself(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("Labels/K", "1")
        with pytest.raises(ValueError, match="redan"):
            await imap_labels.add_label(imap, "Labels/K", ["1"], "K")
        assert bridge.writes() == []

    async def test_refused_copy_fails_every_uid(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        for uid in ("1", "5"):
            bridge.put("INBOX", uid)
        bridge.refuse["COPY"] = "backend error"
        result = await imap_labels.add_label(imap, "INBOX", ["1", "5"], "K")
        assert result["ok"] == []
        assert [f["uid"] for f in result["failed"]] == ["1", "5"]
        assert all("backend error" in f["error"] for f in result["failed"])

    async def test_mail_stays_in_its_folder(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        mid = bridge.put("INBOX", "1", "<a@x>")
        await imap_labels.add_label(imap, "INBOX", ["1"], "K")
        assert set(bridge.views_of(mid)) == {"INBOX", "Labels/K"}


class TestRemoveLabel:
    async def test_expunges_only_the_label_uid(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "42", "<a@x>")
        bridge.put("Labels/K", "7", "<a@x>")
        bridge.put("Labels/K", "8", "<b@x>")
        result = await imap_labels.remove_label(imap, "INBOX", ["42"], "K")
        assert result == {"ok": ["42"], "failed": []}
        assert bridge.writes() == [
            ("UID STORE", "7", "+FLAGS", r"(\Deleted)"),
            ("UID EXPUNGE", "7"),
        ]
        assert bridge.views_of("<a@x>") == ["INBOX"]
        assert "Labels/K" in bridge.views_of("<b@x>")

    async def test_searches_label_by_message_id(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "42", "<a@x>")
        bridge.put("Labels/K", "7", "<a@x>")
        await imap_labels.remove_label(imap, "INBOX", ["42"], "K")
        searches = bridge.sent("SEARCH")
        assert len(searches) == 1
        assert 'HEADER Message-ID "<a@x>"' in searches[0][1]
        # Sökningen görs i etikettens vy
        selects = [c[1] for c in bridge.commands if c[0] == "SELECT"]
        assert selects[-1] == "Labels/K"

    async def test_substring_match_is_not_enough(self, imap_and_bridge):
        # Bridge matchar HEADER som delsträng: "<a@x>" finns inte i "<ba@x>",
        # men "a@x" gör det — exakt jämförelse krävs ändå
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "42", "a@x")
        bridge.put("Labels/K", "8", "<ba@x>")
        result = await imap_labels.remove_label(imap, "INBOX", ["42"], "K")
        assert result["ok"] == []
        assert "har inte etiketten Labels/K" in result["failed"][0]["error"]
        assert bridge.writes() == []

    async def test_same_message_id_but_other_message_is_not_touched(self, imap_and_bridge):
        # T.ex. ett mejl till sig själv: kopian i Sent och den i INBOX är två
        # mejl med samma Message-ID men olika tid eller storlek
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.messages["<a@x>"] = {"date": "01-Jan-2025 10:00:00 +0000", "size": 100, "flags": set()}
        bridge.views["INBOX"]["42"] = "<a@x>"
        # Etikettens mejl är ett annat med samma Message-ID
        bridge.messages["<a@x>#2"] = {"date": "02-Jan-2025 10:00:00 +0000", "size": 200, "flags": set()}
        bridge.views["Labels/K"]["7"] = "<a@x>#2"
        orig = bridge._fetch_lines

        def lines(pairs, items, uid_after):
            out = orig(pairs, items, uid_after)
            return [bytearray(bytes(x).replace(b"<a@x>#2", b"<a@x>")) if isinstance(x, bytearray) else x
                    for x in out]
        bridge._fetch_lines = lines
        result = await imap_labels.remove_label(imap, "INBOX", ["42"], "K")
        assert result["ok"] == []
        assert bridge.writes() == []

    async def test_ambiguous_match_is_refused(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "42", "<a@x>")
        bridge.views["Labels/K"]["7"] = "<a@x>"
        bridge.views["Labels/K"]["9"] = "<a@x>"
        result = await imap_labels.remove_label(imap, "INBOX", ["42"], "K")
        assert result["ok"] == []
        assert "flera" in result["failed"][0]["error"]
        assert bridge.writes() == []

    async def test_message_without_message_id(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "42", "<a@x>")
        orig = bridge._fetch_lines

        def lines(pairs, items, uid_after):
            out = orig(pairs, items, uid_after)
            return [bytearray(b"\r\n") if isinstance(x, bytearray) else x for x in out]
        bridge._fetch_lines = lines
        result = await imap_labels.remove_label(imap, "INBOX", ["42"], "K")
        assert "Message-ID" in result["failed"][0]["error"]
        assert bridge.writes() == []

    async def test_in_label_view_removes_directly(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "42", "<a@x>")
        bridge.put("Labels/K", "7", "<a@x>")
        result = await imap_labels.remove_label(imap, "Labels/K", ["7"], "Labels/K")
        assert result == {"ok": ["7"], "failed": []}
        assert bridge.sent("SEARCH") == []
        assert bridge.writes() == [
            ("UID STORE", "7", "+FLAGS", r"(\Deleted)"),
            ("UID EXPUNGE", "7"),
        ]
        assert bridge.views_of("<a@x>") == ["INBOX"]

    async def test_many_uids_one_expunge(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        for n in range(1, 6):
            bridge.put("INBOX", str(n), f"<m{n}@x>")
            bridge.put("Labels/K", str(100 + n), f"<m{n}@x>")
        result = await imap_labels.remove_label(imap, "INBOX", [str(n) for n in range(1, 6)], "K")
        assert result["ok"] == ["1", "2", "3", "4", "5"]
        expunges = bridge.sent("UID EXPUNGE")
        assert len(expunges) == 1
        assert sorted(expunges[0][1].split(","), key=int) == ["101", "102", "103", "104", "105"]

    async def test_never_plain_expunge(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "42", "<a@x>")
        bridge.put("Labels/K", "7", "<a@x>")
        await imap_labels.remove_label(imap, "INBOX", ["42"], "K")
        assert bridge.sent("EXPUNGE") == []

    async def test_refused_expunge_clears_deleted_flag(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "42", "<a@x>")
        bridge.put("Labels/K", "7", "<a@x>")
        bridge.refuse["EXPUNGE"] = "backend error"
        result = await imap_labels.remove_label(imap, "INBOX", ["42"], "K")
        assert "backend error" in result["failed"][0]["error"]
        assert ("UID STORE", "7", "-FLAGS", r"(\Deleted)") in bridge.writes()
        assert bridge.deleted == set()

    async def test_refused_search_gives_error(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "42", "<a@x>")
        bridge.refuse["SEARCH"] = "search failed"
        with pytest.raises(ValueError, match="search failed"):
            await imap_labels.remove_label(imap, "INBOX", ["42"], "K")
        assert bridge.writes() == []

    async def test_missing_label_refers_to_create_folder(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put("INBOX", "42", "<a@x>")
        with pytest.raises(ValueError, match=r'create_folder\("Labels/K"\)'):
            await imap_labels.remove_label(imap, "INBOX", ["42"], "K")


"""imap_labels (efterfix-tradetikett): delvis nekad EXPUNGE, Message-ID med kommentar och etikettnamn med fel versal."""
import pytest

from protonmail_mcp import imap_labels
from tests.feat_etiketter_bridge import _no, make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


def _expunge_only(bridge, done: set[str], text: str = "backend error"):
    """Bridge tar bort de UID:n i done ur vyn och svarar sedan NO på UID EXPUNGE."""
    original = bridge.client.uid.side_effect

    async def uid(command, *args):
        if command.upper() == "EXPUNGE":
            bridge.commands.append(("UID EXPUNGE", *args))
            for u in done:
                if (bridge.selected, u) in bridge.deleted:
                    bridge._detach(bridge.selected, u)
            return _no(text)
        return await original(command, *args)

    bridge.client.uid.side_effect = uid


class TestPartialExpunge:
    def _two(self, bridge):
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "41", "<a@x>")
        bridge.put("Labels/K", "7", "<a@x>")
        bridge.put("INBOX", "42", "<b@x>")
        bridge.put("Labels/K", "8", "<b@x>")

    async def test_removed_ones_are_ok_and_the_rest_failed(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        self._two(bridge)
        _expunge_only(bridge, {"7"})
        result = await imap_labels.remove_label(imap, "INBOX", ["41", "42"], "K")
        assert result["ok"] == ["41"]
        assert [f["uid"] for f in result["failed"]] == ["42"]
        assert "backend error" in result["failed"][0]["error"]

    async def test_deleted_flag_is_cleared_only_on_the_remaining(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        self._two(bridge)
        _expunge_only(bridge, {"7"})
        await imap_labels.remove_label(imap, "INBOX", ["41", "42"], "K")
        assert ("UID STORE", "8", "-FLAGS", r"(\Deleted)") in bridge.writes()
        assert bridge.deleted == set()

    async def test_in_label_view_too(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        self._two(bridge)
        _expunge_only(bridge, {"8"})
        result = await imap_labels.remove_label(imap, "Labels/K", ["7", "8"], "K")
        assert result["ok"] == ["8"]
        assert [f["uid"] for f in result["failed"]] == ["7"]

    async def test_all_removed_despite_no_counts_as_ok(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        self._two(bridge)
        _expunge_only(bridge, {"7", "8"})
        result = await imap_labels.remove_label(imap, "INBOX", ["41", "42"], "K")
        assert result == {"ok": ["41", "42"], "failed": []}

    async def test_check_that_fails_counts_all_as_failed(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        self._two(bridge)
        _expunge_only(bridge, {"7"})
        inner = bridge.client.uid.side_effect

        async def uid(command, *args):
            # Kontrollen efter EXPUNGE (UID FETCH (UID)) nekas också
            if command.upper() == "FETCH" and args[1] == "(UID)" and bridge.sent("UID EXPUNGE"):
                return _no("fetch refused")
            return await inner(command, *args)

        bridge.client.uid.side_effect = uid
        result = await imap_labels.remove_label(imap, "INBOX", ["41", "42"], "K")
        assert result["ok"] == []
        assert {f["uid"] for f in result["failed"]} == {"41", "42"}
        assert all("kunde inte kontrollera" in f["error"] for f in result["failed"])


def _identity_lines(header: bytes, uid: str = "5") -> list:
    return [
        f'1 FETCH (UID {uid} INTERNALDATE "01-Jan-2026 00:00:00 +0000" RFC822.SIZE 100 '
        f"BODY[HEADER.FIELDS (MESSAGE-ID)] {{{len(header)}}}".encode(),
        bytearray(header),
        b")",
    ]


class TestMessageIdFromHeader:
    @pytest.mark.parametrize("header", [
        b"Message-ID: <abc@x>\r\n (kommentar)\r\n\r\n",
        b"Message-ID:\r\n <abc@x>\r\n\r\n",
        b"Message-ID: <abc@x> (kommentar)\r\n\r\n",
    ])
    def test_folding_and_comments_are_removed(self, header):
        assert imap_labels._parse_identities(_identity_lines(header))["5"]["message_id"] == "<abc@x>"

    def test_eight_bit_id_can_be_sent_to_bridge(self):
        header = b"Message-ID: <r\xc3\xa4ksm\xf6rg\xe5s@evil.example>\r\n\r\n"
        mid = imap_labels._parse_identities(_identity_lines(header))["5"]["message_id"]
        assert mid is not None
        mid.encode("utf-8")  # inga surrogattecken som får aioimaplib att kasta mitt i kommandot

    def test_id_without_angle_brackets_is_kept(self):
        header = b"Message-ID: abc@x\r\n\r\n"
        assert imap_labels._parse_identities(_identity_lines(header))["5"]["message_id"] == "abc@x"

    def test_blank_id_is_none(self):
        header = b"Message-ID:   \r\n\r\n"
        assert imap_labels._parse_identities(_identity_lines(header))["5"]["message_id"] is None


class TestUnusableMessageIdIsPerUid:
    async def test_folded_comment_does_not_refuse_the_whole_call(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        raw = "<c@x>\r\n (kommentar)"
        bridge.put("INBOX", "41", raw)
        bridge.put("Labels/K", "9", raw)
        bridge.put("INBOX", "42", "<b@x>")
        bridge.put("Labels/K", "8", "<b@x>")
        result = await imap_labels.remove_label(imap, "INBOX", ["41", "42"], "K")
        assert result == {"ok": ["41", "42"], "failed": []}
        assert bridge.views["Labels/K"] == {}

    async def test_unusable_id_fails_only_that_uid(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/K")
        bridge.put("INBOX", "41", "   ")
        bridge.put("INBOX", "42", "<b@x>")
        bridge.put("Labels/K", "8", "<b@x>")
        result = await imap_labels.remove_label(imap, "INBOX", ["41", "42"], "K")
        assert result["ok"] == ["42"]
        assert [f["uid"] for f in result["failed"]] == ["41"]
        assert "saknar Message-ID" in result["failed"][0]["error"]


class TestLabelCase:
    async def test_add_label_uses_the_existing_label_with_other_case(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/Faktura")
        bridge.put("INBOX", "42", "<a@x>")
        result = await imap_labels.add_label(imap, "INBOX", ["42"], "faktura")
        assert result == {"ok": ["42"], "failed": []}
        assert ("UID COPY", "42", '"Labels/Faktura"') in bridge.writes()
        assert "Labels/faktura" not in bridge.views

    async def test_remove_label_uses_the_existing_label_with_other_case(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/Faktura")
        bridge.put("INBOX", "42", "<a@x>")
        bridge.put("Labels/Faktura", "7", "<a@x>")
        result = await imap_labels.remove_label(imap, "INBOX", ["42"], "labels/FAKTURA")
        assert result == {"ok": ["42"], "failed": []}
        assert bridge.views["Labels/Faktura"] == {}

    async def test_label_view_as_mailbox_with_other_case(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/Faktura")
        bridge.put("INBOX", "42", "<a@x>")
        bridge.put("Labels/Faktura", "7", "<a@x>")
        result = await imap_labels.remove_label(imap, "Labels/faktura", ["7"], "faktura")
        assert result == {"ok": ["7"], "failed": []}

    async def test_exact_match_wins(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/Faktura")
        bridge.add_label("Labels/faktura")
        bridge.put("INBOX", "42", "<a@x>")
        await imap_labels.add_label(imap, "INBOX", ["42"], "faktura")
        assert ("UID COPY", "42", '"Labels/faktura"') in bridge.writes()

    async def test_ambiguous_case_variants_are_refused_without_create_advice(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/Faktura")
        bridge.add_label("Labels/FAKTURA")
        bridge.put("INBOX", "42", "<a@x>")
        with pytest.raises(ValueError) as exc:
            await imap_labels.add_label(imap, "INBOX", ["42"], "faktura")
        assert "Labels/Faktura" in str(exc.value) and "Labels/FAKTURA" in str(exc.value)
        assert "create_folder" not in str(exc.value)
        assert bridge.writes() == []

    async def test_missing_label_still_refers_to_create_folder(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.add_label("Labels/Kvitton")
        bridge.put("INBOX", "42", "<a@x>")
        with pytest.raises(ValueError, match=r'create_folder\("Labels/Faktura"\)'):
            await imap_labels.add_label(imap, "INBOX", ["42"], "Faktura")

    async def test_folder_with_same_name_is_not_a_label(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.views["Folders/faktura"] = {}
        bridge.put("INBOX", "42", "<a@x>")
        with pytest.raises(ValueError, match="create_folder"):
            await imap_labels.add_label(imap, "INBOX", ["42"], "faktura")

"""Enhetstester: lokal filtrering av SUBJECT/FROM mot avkodade headers (fix-sok, N4)."""
import unicodedata

import pytest

from protonmail_mcp import imap_client as imap_module
from protonmail_mcp.imap_client import IMAPClient, _header_matches, _parse_fetch_metadata
from tests.fix_sok_fakebox import FakeMailbox, imap_mock


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    imap = IMAPClient(Settings(_env_file=None))
    imap._client = imap_mock()
    return imap


def _sent_criteria(client):
    return [c.args[0] for c in client._client.search.call_args_list]


class TestHeaderMatches:
    def test_case_insensitive_substring(self):
        assert _header_matches("Svenska Fjällklubben", "FJÄLL")

    def test_nfd_term_matches_nfc_header(self):
        assert _header_matches("Fjällklubben", unicodedata.normalize("NFD", "fjäll"))

    def test_no_match(self):
        assert not _header_matches("Hej", "då")


class TestLocalFiltering:
    async def test_text_terms_are_not_sent_to_server(self, client):
        box = FakeMailbox()
        box.add(11041, "=?utf-8?q?Svenska_Fj=C3=A4llklubben?=")
        box.install(client)
        result = await client.search_messages("INBOX", subject="fjällklubben", since="2024-01-01", unseen=True)
        assert [m["uid"] for m in result["messages"]] == ["11041"]
        assert _sent_criteria(client) == ["SINCE 01-Jan-2024 UNSEEN"]

    async def test_complete_and_exact_total_within_limit(self, client):
        box = FakeMailbox()
        for uid in (1, 2, 3):
            box.add(uid, "=?utf-8?q?R=C3=A4kning?=")
        box.add(4, "Annat")
        box.install(client)
        result = await client.search_messages("INBOX", subject="räkning", max_results=2)
        assert [m["uid"] for m in result["messages"]] == ["3", "2"]
        assert result["total"] == 3
        assert result["has_more"] is True
        assert result["complete"] is True
        assert result["note"] is None

    async def test_both_from_and_subject_must_match(self, client):
        box = FakeMailbox()
        box.add(1, "Möte", "=?utf-8?q?=C3=85sa?= <asa@x.se>")
        box.add(2, "Möte", "bo@x.se")
        box.add(3, "Lunch", "=?utf-8?q?=C3=85sa?= <asa@x.se>")
        box.install(client)
        result = await client.search_messages("INBOX", subject="möte", from_addr="åsa")
        assert [m["uid"] for m in result["messages"]] == ["1"]

    async def test_non_ascii_over_limit_is_incomplete_without_extra_search(self, client, monkeypatch):
        monkeypatch.setattr(imap_module, "_LOCAL_SCAN_LIMIT", 10)
        box = FakeMailbox()
        box.add(1, "=?utf-8?q?=C3=84ldre?=")  # utanför fönstret
        box.fill(15)
        box.install(client)
        result = await client.search_messages("INBOX", subject="äldre")
        assert result["messages"] == []
        assert result["complete"] is False
        assert "10" in result["note"] and "16" in result["note"]
        assert _sent_criteria(client) == ["ALL"]
        fetched = sum(len(c.args[0].split(",")) for c in client._client.fetch.call_args_list)
        assert fetched == 10

    async def test_ascii_over_limit_asks_server_for_older_raw_hits(self, client, monkeypatch):
        monkeypatch.setattr(imap_module, "_LOCAL_SCAN_LIMIT", 10)
        box = FakeMailbox()
        box.add(1, "Kvitto 2019")
        box.add(2, "=?utf-8?B?a3ZpdHRvIGZyw6VuIGJ1dGlr?=")  # äldre och B-kodat: missas, som noten säger
        box.fill(15, "Nyhetsbrev")
        box.install(client)
        result = await client.search_messages("INBOX", subject="kvitto")
        assert [m["uid"] for m in result["messages"]] == ["1"]
        assert result["complete"] is False
        assert _sent_criteria(client) == ["ALL", 'SUBJECT "kvitto"']

    async def test_raw_server_hits_are_verified_locally(self, client, monkeypatch):
        monkeypatch.setattr(imap_module, "_LOCAL_SCAN_LIMIT", 2)
        box = FakeMailbox()
        box.add(1, "=?utf-8?q?Hej?=")  # rått "utf" men avkodat "Hej"
        box.fill(3)
        box.install(client)
        result = await client.search_messages("INBOX", subject="utf")
        assert result["messages"] == []

    async def test_enough_matches_in_window_skips_older_search(self, client, monkeypatch):
        monkeypatch.setattr(imap_module, "_LOCAL_SCAN_LIMIT", 10)
        box = FakeMailbox()
        box.fill(15, "Kvitto")
        box.install(client)
        result = await client.search_messages("INBOX", subject="kvitto", max_results=5)
        assert len(result["messages"]) == 5
        assert result["has_more"] is True
        assert _sent_criteria(client) == ["ALL"]


class TestRaw8BitHeaders:
    def test_raw_utf8_header_is_decoded_not_replacement_chars(self):
        lines = [
            b"1 FETCH (UID 1 FLAGS () BODY[HEADER.FIELDS (SUBJECT FROM)] {40}",
            bytearray("Subject: Möte i Göteborg\r\nFrom: Åsa <a@x.se>\r\n\r\n".encode()),
            b")",
        ]
        msg = _parse_fetch_metadata(lines)[0]
        assert (msg["subject"], msg["from"]) == ("Möte i Göteborg", "Åsa <a@x.se>")

    def test_invalid_utf8_falls_back_to_latin1(self):
        lines = [
            b"1 FETCH (UID 1 FLAGS () BODY[HEADER.FIELDS (SUBJECT)] {20}",
            bytearray("Subject: Möte\r\n\r\n".encode("latin-1")),
            b")",
        ]
        assert _parse_fetch_metadata(lines)[0]["subject"] == "Möte"


class TestWithoutTextTerms:
    async def test_server_side_only_with_exact_total(self, client):
        box = FakeMailbox()
        box.fill(7)
        box.install(client)
        result = await client.search_messages("INBOX", unseen=False, max_results=3)
        assert len(result["messages"]) == 3
        assert result["total"] == 7
        assert result["has_more"] is True
        assert result["complete"] is True
        assert _sent_criteria(client) == ["SEEN"]

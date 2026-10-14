"""Enhetstester: _parse_fetch_metadata tål oombedda svar, dubbletter och UID efter literalen (fix-sok)."""
from protonmail_mcp.imap_client import _parse_fetch_metadata


def _msg(seq, uid, subject, flags=""):
    return [
        f"{seq} FETCH (UID {uid} FLAGS ({flags}) BODY[HEADER.FIELDS (DATE FROM SUBJECT)] {{40}}".encode(),
        bytearray(f"Subject: {subject}\r\n\r\n".encode()),
        b")",
    ]


class TestUnsolicitedFetch:
    def test_fetch_without_header_literal_is_ignored(self):
        lines = _msg(1, 20, "msg20") + [b"1 FETCH (UID 999 FLAGS (\\Seen))"] + _msg(2, 30, "msg30")
        assert [(m["uid"], m["subject"]) for m in _parse_fetch_metadata(lines)] == [
            ("20", "msg20"), ("30", "msg30")]

    def test_flags_only_fetch_without_uid_is_ignored(self):
        lines = [b"3 FETCH (FLAGS (\\Seen))"] + _msg(1, 20, "msg20")
        assert [m["uid"] for m in _parse_fetch_metadata(lines)] == ["20"]

    def test_duplicate_uid_appears_once(self):
        lines = _msg(1, 20, "msg20") + _msg(1, 20, "msg20")
        assert [m["uid"] for m in _parse_fetch_metadata(lines)] == ["20"]


class TestUidAfterLiteral:
    def test_uid_after_literal_like_bridge_uid_fetch(self):
        lines = [
            b"6718 FETCH (FLAGS () BODY[HEADER.FIELDS (DATE)] {41}",
            bytearray(b"Subject: Hej\r\n\r\n"),
            b" UID 11319)",
        ]
        result = _parse_fetch_metadata(lines)
        assert [(m["uid"], m["subject"]) for m in result] == [("11319", "Hej")]

    def test_flags_after_literal(self):
        lines = [
            b"7 FETCH (BODY[HEADER.FIELDS (DATE)] {41}",
            bytearray(b"Subject: Hej\r\n\r\n"),
            b" UID 5 FLAGS (\\Seen \\Flagged))",
        ]
        result = _parse_fetch_metadata(lines)
        assert result[0]["uid"] == "5"
        assert result[0]["flags"] == ["\\Seen", "\\Flagged"]

    def test_closing_paren_of_one_message_does_not_leak_into_next(self):
        lines = _msg(1, 20, "Ett", "\\Seen") + _msg(2, 30, "Två")
        result = _parse_fetch_metadata(lines)
        assert [(m["uid"], m["flags"]) for m in result] == [("20", ["\\Seen"]), ("30", [])]

"""Backslash och citattecken i mappnamn: avescapas i LIST, tillåts och escapas tillbaka."""
import pytest

from protonmail_mcp.imap_client import _parse_list_line, _quote_mailbox, _validate_mailbox


class TestParseListLineUnescapes:
    def test_escaped_backslash(self):
        line = '(\\Unmarked) "/" "Labels/Neomeda\\\\/Kvitto\\\\/Faktura"'
        assert _parse_list_line(line) == "Labels/Neomeda\\/Kvitto\\/Faktura"

    def test_escaped_quote(self):
        assert _parse_list_line('(\\Unmarked) "/" "Labels/Citat \\"x\\""') == 'Labels/Citat "x"'

    def test_trailing_escaped_backslash(self):
        """Pseudo-föräldrar under Labels/ slutar med ett backslash."""
        assert _parse_list_line('(\\Noselect) "/" "Labels/Neomeda\\\\"') == "Labels/Neomeda\\"

    def test_unquoted_atom(self):
        assert _parse_list_line('(\\HasNoChildren) "/" Sent') == "Sent"

    def test_nil_delimiter(self):
        assert _parse_list_line('(\\Noselect) NIL "Folders"') == "Folders"


class TestValidateMailboxAllowsEscapable:
    def test_allows_backslash(self):
        assert _validate_mailbox("Labels/Neomeda\\/Kvitto") == "Labels/Neomeda\\/Kvitto"

    def test_allows_double_quote(self):
        assert _validate_mailbox('Labels/Citat "x"') == 'Labels/Citat "x"'

    @pytest.mark.parametrize("name", ["", "IN\rBOX", "IN\nBOX", "INBOX\x00", "IN\x7fBOX", "a\tb"])
    def test_still_rejects_control_chars_and_empty(self, name):
        with pytest.raises(ValueError, match="Ogiltigt mailbox-namn"):
            _validate_mailbox(name)


class TestQuoteMailboxRoundTrip:
    @pytest.mark.parametrize(
        "wire",
        [
            "INBOX",
            "Labels/Neomeda\\\\/Kvitto\\\\/Faktura",
            "Labels/Neomeda\\\\",
            'Labels/Citat \\"x\\"',
        ],
    )
    def test_listed_name_is_sent_back_unchanged(self, wire):
        name = _parse_list_line(f'(\\Unmarked) "/" "{wire}"')
        assert _quote_mailbox(name) == f'"{wire}"'

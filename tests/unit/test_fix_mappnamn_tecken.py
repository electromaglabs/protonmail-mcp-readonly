"""N10: %, * och .. är giltiga i Proton-mappnamn; kontrolltecken är det inte."""
import pytest

from protonmail_mcp.imap_client import _quote_mailbox, _validate_mailbox


@pytest.mark.parametrize(
    "name", ["Labels/100% klart", "Folders/Viktigt*", "Folders/v1..v2", "..", "*", "%"]
)
def test_allows_percent_asterisk_and_dotdot(name):
    assert _validate_mailbox(name) == name
    assert _quote_mailbox(name) == f'"{name}"'


@pytest.mark.parametrize("name", ["INBOX\r\nA1 DELETE INBOX", "INBOX\x00", "IN\x1bBOX"])
def test_still_rejects_control_chars(name):
    with pytest.raises(ValueError, match="Ogiltigt mailbox-namn"):
        _quote_mailbox(name)

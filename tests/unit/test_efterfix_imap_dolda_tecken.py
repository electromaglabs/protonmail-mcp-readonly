"""_validate_uid och _validate_mailbox ska matcha hela värdet (S6).

I Python matchar "$" även före ett avslutande "\\n", och "\\d" matchar alla
Unicode-siffror ("１２３", "٣").
"""
import pytest

from protonmail_mcp.imap_client import _validate_mailbox, _validate_uid


@pytest.mark.parametrize("uid", ["123\n", "１２３", "٣", "12\n3", "1\r\n"])
def test_uid_rejects_hidden_characters(uid):
    with pytest.raises(ValueError, match="Ogiltigt UID"):
        _validate_uid(uid)


def test_uid_still_accepts_ascii_digits():
    assert _validate_uid("4711") == "4711"


@pytest.mark.parametrize("name", ["INBOX\n", "Trash\n", "Folders/A\r\n"])
def test_mailbox_rejects_trailing_newline(name):
    with pytest.raises(ValueError, match="Ogiltigt mailbox-namn"):
        _validate_mailbox(name)


def test_mailbox_still_accepts_unicode_names():
    assert _validate_mailbox("Folders/Näs ٣") == "Folders/Näs ٣"

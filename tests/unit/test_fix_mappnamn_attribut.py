"""N6: list_mailboxes tar hänsyn till LIST-attributen (\\Noselect och special-use)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient, _parse_list_entry
from protonmail_mcp.mailbox_names import describe_mailbox

# LIST-rader som Bridge skickar dem (live), med förväntat resultat
LIVE = [
    ('(\\Noinferiors \\Unmarked) "/" "INBOX"', "INBOX", "system", True, None),
    ('(\\Drafts \\Noinferiors \\Unmarked) "/" "Drafts"', "Drafts", "system", True, "\\Drafts"),
    ('(\\Noinferiors \\Sent \\Unmarked) "/" "Sent"', "Sent", "system", True, "\\Sent"),
    ('(\\Flagged \\Noinferiors \\Unmarked) "/" "Starred"', "Starred", "system", True, "\\Flagged"),
    ('(\\Archive \\Noinferiors \\Unmarked) "/" "Archive"', "Archive", "system", True, "\\Archive"),
    ('(\\Junk \\Noinferiors \\Unmarked) "/" "Spam"', "Spam", "system", True, "\\Junk"),
    ('(\\Noinferiors \\Trash \\Unmarked) "/" "Trash"', "Trash", "system", True, "\\Trash"),
    ('(\\All \\Noinferiors \\Unmarked) "/" "All Mail"', "All Mail", "system", True, "\\All"),
    ('(\\Noselect \\Unmarked) "/" "Folders"', "Folders", "container", False, None),
    ('(\\Noselect \\Unmarked) "/" "Labels"', "Labels", "container", False, None),
    ('(\\Noselect) "/" "Labels/Neomeda\\\\"', "Labels/Neomeda\\", "container", False, None),
    ('(\\Noselect) "/" "Labels/[Superhuman]\\\\/AI\\\\"', "Labels/[Superhuman]\\/AI\\", "container", False, None),
    ('(\\Marked) "/" "Folders/Jobb"', "Folders/Jobb", "folder", True, None),
    ('(\\Unmarked) "/" "Folders/F&APY-reningar"', "Folders/Föreningar", "folder", True, None),
    ('(\\Unmarked) "/" "Labels/Gr&APY-nvik"', "Labels/Grönvik", "label", True, None),
    ('(\\Unmarked) "/" "Labels/Neomeda\\\\/Kvitto\\\\/Faktura"', "Labels/Neomeda\\/Kvitto\\/Faktura", "label", True, None),
]


class TestParseListEntry:
    def test_returns_attributes_and_name(self):
        assert _parse_list_entry('(\\Drafts \\Noinferiors) "/" "Drafts"') == (
            ["\\Drafts", "\\Noinferiors"],
            "Drafts",
        )

    def test_empty_attributes(self):
        assert _parse_list_entry('() "/" "INBOX"') == ([], "INBOX")

    def test_no_match(self):
        assert _parse_list_entry("LIST completed") is None


class TestDescribeMailbox:
    def test_attributes_case_insensitive(self):
        assert describe_mailbox("Drafts", ["\\drafts"]) == {
            "name": "Drafts", "type": "system", "selectable": True, "special_use": "\\Drafts",
        }
        assert describe_mailbox("Folders", ["\\NOSELECT"])["selectable"] is False

    def test_nonexistent_is_not_selectable(self):
        """RFC 5258: \\NonExistent innebär \\Noselect."""
        info = describe_mailbox("Folders/Borta", ["\\NonExistent"])
        assert info["selectable"] is False
        assert info["type"] == "container"

    def test_unknown_attributes_ignored(self):
        assert describe_mailbox("Labels/X", ["\\Marked", "\\HasChildren"]) == {
            "name": "Labels/X", "type": "label", "selectable": True, "special_use": None,
        }


class TestListMailboxesAttributes:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        imap = IMAPClient(Settings())
        imap._client = AsyncMock()
        imap._client.noop.return_value = SimpleNamespace(result="OK", lines=[])
        imap._client.list.return_value = SimpleNamespace(
            result="OK", lines=[row[0] for row in LIVE] + ["LIST completed"]
        )
        return imap

    async def test_every_mailbox_described(self, client):
        result = await client.list_mailboxes()
        assert result == [
            {"name": name, "type": typ, "selectable": sel, "special_use": su}
            for _, name, typ, sel, su in LIVE
        ]

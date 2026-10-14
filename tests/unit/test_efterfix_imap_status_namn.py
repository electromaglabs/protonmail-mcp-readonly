"""STATUS: antalet läses ur den avslutande parentesen, aldrig ur mappnamnet (K1/F1).

Bridge svarar '"Folders/Messages 0" (MESSAGES 5)'. Det gamla mönstret
(\\w+)\\s+(\\d+) över hela raden tog "Messages 0" ur namnet.
"""
from types import SimpleNamespace

import pytest

from protonmail_mcp.imap_client import _status_messages
from tests.fix_flytta_bridge import make_client


def _resp(*lines):
    return SimpleNamespace(result="OK", lines=[*lines, b"STATUS completed"])


@pytest.mark.parametrize("line, expected", [
    (b'STATUS "Folders/Messages 0" (MESSAGES 5)', 5),
    (b'"Folders/Messages 2024" (MESSAGES 0 UNSEEN 0)', 0),
    (b'"Labels/messages 1" (UNSEEN 0 MESSAGES 12)', 12),
    (b'"Folders/a (MESSAGES 3)" (MESSAGES 7)', 7),
])
def test_count_comes_from_status_list(line, expected):
    assert _status_messages(_resp(line)) == expected


def test_name_sent_as_literal_is_not_parsed():
    # En literal (bytearray) är mappnamnet, aldrig statuslistan
    resp = _resp(b"STATUS {22}", bytearray(b"Folders/x (MESSAGES 0)"), b" (MESSAGES 4)")
    assert _status_messages(resp) == 4


def test_missing_count_is_none():
    assert _status_messages(_resp(b'"Folders/Messages 3" (UNSEEN 0)')) is None


async def test_delete_folder_with_messages_in_name_refuses(monkeypatch):
    imap, bridge = make_client(monkeypatch)
    for uid in ("1", "2", "3", "4", "5"):
        bridge.add("Folders/Messages 0", uid)
    with pytest.raises(ValueError, match=r"inte tom \(5 mejl\)"):
        await imap.delete_folder("Folders/Messages 0")
    assert bridge.sent("DELETE") == []


async def test_mailbox_status_ignores_name(monkeypatch):
    imap, bridge = make_client(monkeypatch)
    bridge.client.status.side_effect = None
    bridge.client.status.return_value = _resp(b'"Folders/Unseen 9 (MESSAGES 8)" (MESSAGES 2 UNSEEN 1)')
    assert await imap.get_mailbox_status("Folders/Unseen 9 (MESSAGES 8)") == {"messages": 2, "unseen": 1}

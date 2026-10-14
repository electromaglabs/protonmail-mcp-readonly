"""IMAPClient.delete_folder: STATUS MESSAGES först, vägra om mappen inte är tom."""
from types import SimpleNamespace

import pytest

from tests.fix_flytta_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


async def test_deletes_empty_folder_after_status(imap_and_bridge):
    imap, bridge = imap_and_bridge
    bridge.mailboxes["Folders/X"] = set()
    assert await imap.delete_folder("Folders/X") is True
    assert bridge.names() == ["STATUS", "DELETE"]
    assert bridge.sent("STATUS") == [("STATUS", "Folders/X", "(MESSAGES)")]


async def test_refuses_non_empty_folder(imap_and_bridge):
    imap, bridge = imap_and_bridge
    bridge.add("Folders/X", "1")
    bridge.add("Folders/X", "2")
    with pytest.raises(ValueError, match="inte tom.*2 mejl"):
        await imap.delete_folder("Folders/X")
    assert bridge.sent("DELETE") == []


async def test_refuses_non_empty_label(imap_and_bridge):
    imap, bridge = imap_and_bridge
    bridge.add("Labels/X", "1")
    with pytest.raises(ValueError, match="etiketten"):
        await imap.delete_folder("Labels/X")
    assert bridge.sent("DELETE") == []


async def test_force_deletes_non_empty(imap_and_bridge):
    imap, bridge = imap_and_bridge
    bridge.add("Labels/X", "1")
    assert await imap.delete_folder("Labels/X", force=True) is True
    assert bridge.sent("DELETE") == [("DELETE", "Labels/X")]


async def test_missing_folder_raises_without_delete(imap_and_bridge):
    imap, bridge = imap_and_bridge
    with pytest.raises(ValueError, match="no such mailbox"):
        await imap.delete_folder("Folders/Saknas")
    assert bridge.sent("DELETE") == []


async def test_unparseable_status_is_not_treated_as_empty(imap_and_bridge):
    imap, bridge = imap_and_bridge
    bridge.client.status.side_effect = None
    bridge.client.status.return_value = SimpleNamespace(result="OK", lines=[b"STATUS completed"])
    with pytest.raises(ValueError, match="antal"):
        await imap.delete_folder("Folders/X")
    bridge.client.delete.assert_not_called()

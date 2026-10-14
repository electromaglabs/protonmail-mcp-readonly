"""delete_folder kontrollerar undermappar med LIST före DELETE (S3).

Bridge (gluon) kontrollerar inte undermappar vid DELETE, och hur Proton
hanterar dem när föräldern tas bort är inte verifierat.
"""
import pytest

from tests.fix_flytta_bridge import make_client


@pytest.fixture
def client(monkeypatch):
    return make_client(monkeypatch)


async def test_refuses_parent_with_subfolders(client):
    imap, bridge = client
    bridge.mailboxes["Folders/A"] = set()
    bridge.add("Folders/A/B", "1")
    bridge.mailboxes["Folders/A/B/C"] = set()
    with pytest.raises(ValueError, match=r"2 undermappar.*Folders/A/B.*force=True"):
        await imap.delete_folder("Folders/A")
    assert bridge.sent("DELETE") == []


async def test_list_pattern_is_encoded_and_quoted(client):
    imap, bridge = client
    bridge.mailboxes["Folders/N&AOQ-s"] = set()  # låtsas-Bridgen lagrar trådnamnet
    await imap.delete_folder("Folders/Näs")
    pattern = bridge.client.list.call_args.args[1]
    assert pattern == '"Folders/N&AOQ-s/*"'


async def test_wildcards_in_name_do_not_count_other_folders(client):
    imap, bridge = client
    bridge.mailboxes["Folders/A*"] = set()
    bridge.add("Folders/Ab/c", "1")
    assert await imap.delete_folder("Folders/A*") is True


async def test_refused_list_stops_delete(client):
    imap, bridge = client
    bridge.mailboxes["Folders/A"] = set()
    bridge.refuse["LIST"] = "sync in progress"
    with pytest.raises(ValueError, match="sync in progress"):
        await imap.delete_folder("Folders/A")
    assert bridge.sent("DELETE") == []


async def test_force_skips_check(client):
    imap, bridge = client
    bridge.mailboxes["Folders/A"] = set()
    bridge.add("Folders/A/B", "1")
    assert await imap.delete_folder("Folders/A", force=True) is True
    assert bridge.sent("DELETE") == [("DELETE", "Folders/A")]

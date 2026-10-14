"""\\Noselect-behållare ger fel i stället för {0, 0} eller en tom sida (F4/K8).

Bridge svarar OK med 0 mejl på SELECT och STATUS av Folders och Labels.
Klienten frågar LIST om just det namnet, men bara när mappen ser tom ut.
"""
import pytest

from tests.fix_flytta_bridge import make_client


@pytest.fixture
def client(monkeypatch):
    imap, bridge = make_client(monkeypatch)
    for name in ("Folders", "Labels"):
        bridge.containers.add(name)
        bridge.mailboxes[name] = set()
    return imap, bridge


@pytest.mark.parametrize("call", [
    lambda c: c.get_mailbox_status("Folders"),
    lambda c: c.list_messages("Labels"),
    lambda c: c.search_messages("Folders", unseen=True),
    lambda c: c.get_message("Labels", "1"),
    lambda c: c.get_message_headers("Folders", "1"),
])
async def test_container_gives_error(client, call):
    imap, bridge = client
    with pytest.raises(ValueError, match="är en behållare, inte en mapp"):
        await call(imap)


async def test_list_asks_for_the_exact_name(client):
    imap, bridge = client
    with pytest.raises(ValueError):
        await imap.get_mailbox_status("Folders")
    assert bridge.sent("LIST") == [("LIST", "Folders")]


async def test_wildcard_name_only_matches_itself(client):
    imap, bridge = client
    # "Folders/A*" är en vanlig tom mapp; LIST-mönstret matchar även behållaren "Folders/Ab"
    bridge.mailboxes["Folders/A*"] = set()
    bridge.containers.add("Folders/Ab")
    assert await imap.get_mailbox_status("Folders/A*") == {"messages": 0, "unseen": 0}


async def test_refused_list_keeps_the_answer(client):
    imap, bridge = client
    bridge.mailboxes["Folders/Tom"] = set()
    bridge.refuse["LIST"] = "sync in progress"
    assert await imap.get_mailbox_status("Folders/Tom") == {"messages": 0, "unseen": 0}


async def test_non_empty_mailbox_sends_no_list(client):
    imap, bridge = client
    bridge.add("INBOX", "7")
    assert await imap.get_mailbox_status("INBOX") == {"messages": 1, "unseen": 0}
    assert bridge.sent("LIST") == []

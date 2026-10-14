"""Tester för punkter som granskningen visade var otestade (gransk-tackning G3, T1).

- G3: träffar i det lokalt kontrollerade fönstret får inte räknas igen när
  servern söker bland äldre brev, och has_more ska vara sant när äldre
  serverträffar inte hann kontrolleras.
- T1: själva värdet på _FETCH_CHUNK_SIZE skyddar mot RecursionError i
  aioimaplib (~3000 brev i ett svar) och testades inte.
"""
import pytest

from protonmail_mcp import imap_client
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from tests.fix_sok_fakebox import FakeMailbox, imap_mock


def test_fetch_chunk_size_stays_below_recursion_limit():
    assert 1 <= imap_client._FETCH_CHUNK_SIZE <= 200


@pytest.fixture
def client():
    imap = IMAPClient(Settings(username="u", password="p", _env_file=None))
    imap._client = imap_mock()
    return imap


async def test_hits_in_window_are_not_counted_twice(client):
    box = FakeMailbox()
    box.add(1, "Hit gammal")                      # seq 1, utanför fönstret
    box.fill(imap_client._LOCAL_SCAN_LIMIT + 3)   # seq 2 … 1004
    box.add(9999, "Hit ny")                       # seq 1005, i fönstret
    box.install(client)
    result = await client.search_messages("INBOX", subject="Hit", max_results=10)
    uids = [m["uid"] for m in result["messages"]]
    assert uids == ["9999", "1"]
    assert result["total"] == 2
    assert result["has_more"] is False


async def test_unchecked_older_hits_give_has_more(client, monkeypatch):
    # Fler äldre serverträffar än max_results: de äldsta hinner inte kontrolleras.
    # (has_more blir då sant redan av total > max_results; more-flaggan i
    # _search_result kan inte ensam avgöra utfallet, se rapporten.)
    monkeypatch.setattr(imap_client, "_FETCH_CHUNK_SIZE", 5)
    box = FakeMailbox()
    for i in range(12):
        box.add(100 + i, f"Hit {i}")              # seq 1 … 12, utanför fönstret
    box.fill(imap_client._LOCAL_SCAN_LIMIT)       # fönstret: inga träffar
    box.install(client)
    result = await client.search_messages("INBOX", subject="Hit", max_results=3)
    assert result["has_more"] is True
    assert result["complete"] is False
    assert [m["uid"] for m in result["messages"]] == ["111", "110", "109"]

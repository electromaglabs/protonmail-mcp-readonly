"""imap_labels.set_starred: stjärnmärkning med \\Flagged (Starred i Proton)."""
import pytest

from protonmail_mcp import imap_labels
from tests.feat_etiketter_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


class TestStar:
    async def test_flag_and_unflag(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put("INBOX", "1", "<a@x>")
        bridge.put("INBOX", "2", "<b@x>")
        assert await imap_labels.set_starred(imap, "INBOX", ["1", "2"], True) == {"ok": ["1", "2"], "failed": []}
        assert bridge.messages["<a@x>"]["flags"] == {r"\Flagged"}
        await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert bridge.writes()[-1] == ("UID STORE", "1", "-FLAGS", r"(\Flagged)")
        assert bridge.messages["<a@x>"]["flags"] == set()

    async def test_missing_uid_and_refusal(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put("INBOX", "1", "<a@x>")
        res = await imap_labels.set_starred(imap, "INBOX", ["1", "2"], True)
        assert res["ok"] == ["1"]
        assert "Inget meddelande med UID 2 i INBOX" in res["failed"][0]["error"]
        bridge.refuse["STORE"] = "backend error"
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res["ok"] == []
        assert "backend error" in res["failed"][0]["error"]

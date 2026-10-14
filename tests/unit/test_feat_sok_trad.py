"""Enhetstester för get_thread (feat-sok): konversationer byggda av Message-ID-kedjan."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.imap_threads import (
    _message_ids,
    _thread_criteria,
    get_thread,
)
from protonmail_mcp.server import mcp
from tests.feat_sok_fakebridge import FakeBridge, FakeMessage


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    fake = FakeBridge()
    imap = IMAPClient(Settings())
    imap._client = fake.client()
    fake.imap = imap
    return fake


def _msg(uid, mid, date, irt="", refs="", subject="Ämne", **extra):
    return FakeMessage(uid=uid, headers={
        "From": "a@example.com", "To": "b@example.com", "Subject": subject,
        "Date": date, "Message-ID": mid, "In-Reply-To": irt, "References": refs, **extra,
    })


def _start(bridge, uid, mid, **kw):
    original = next(m for m in bridge.boxes["All Mail"] if m.header("Message-ID") == mid)
    bridge.add("INBOX", FakeMessage(uid=uid, headers={**original.headers, **kw}))


def _uids(result):
    return [m["uid"] for m in result["messages"]]


class TestMessageIds:
    def test_extracts_in_order_without_duplicates(self):
        assert _message_ids("<a@x>", "<b@x>", "<a@x> <c@x>\r\n <b@x>") == ["<a@x>", "<b@x>", "<c@x>"]

    def test_ignores_empty_and_garbage(self):
        assert _message_ids("", None, "inget id", "<>") == []

    def test_refuses_ids_with_quotes_or_control_characters(self):
        assert _message_ids('<a"b@x>', "<a\x00b@x>") == []

    def test_proton_internal_ids_are_skipped(self):
        # Bridge lägger till Protons eget ID i References; det är aldrig ett Message-ID
        refs = "<abc==@protonmail.internalid> <a@x>"
        assert _message_ids(refs) == ["<a@x>"]


class TestThreadCriteria:
    def test_one_id_searches_message_id_in_reply_to_and_references(self):
        command = " ".join(_thread_criteria(["<a@x>"]))
        assert command == (
            'OR HEADER Message-ID "<a@x>" OR HEADER In-Reply-To "<a@x>" HEADER References "<a@x>"'
        )

    def test_or_is_balanced_for_many_ids(self):
        criteria = _thread_criteria(["<a@x>", "<b@x>", "<c@x>"])
        assert criteria.count("HEADER") == 9
        assert criteria.count("OR") == 8


class TestGetThread:
    def _fill(self, bridge):
        bridge.add("All Mail", _msg(1, "<a@x>", "Mon, 05 Oct 2026 09:00:00 +0200"))
        bridge.add("All Mail", _msg(2, "<b@x>", "Mon, 05 Oct 2026 10:00:00 +0200", "<a@x>", "<a@x>"))
        bridge.add("All Mail", _msg(3, "<c@x>", "Tue, 06 Oct 2026 08:00:00 +0200", "<b@x>", "<a@x> <b@x>"))
        bridge.add("All Mail", _msg(4, "<d@x>", "Tue, 06 Oct 2026 09:00:00 +0200"))
        # Svarar bara med In-Reply-To (vissa klienter skriver ingen References)
        bridge.add("All Mail", _msg(5, "<e@x>", "Wed, 07 Oct 2026 08:00:00 +0200", "<c@x>"))

    async def test_whole_chain_from_the_first_message(self, bridge):
        self._fill(bridge)
        _start(bridge, 70, "<a@x>")
        result = await get_thread(bridge.imap, "70", "INBOX")
        assert _uids(result) == ["1", "2", "3", "5"]
        assert result["complete"] is True and result["total"] == 4

    async def test_result_has_metadata_for_get_email(self, bridge):
        self._fill(bridge)
        _start(bridge, 70, "<b@x>")
        result = await get_thread(bridge.imap, "70", "INBOX")
        first = result["messages"][0]
        assert result["mailbox"] == "All Mail"
        assert first["mailbox"] == "All Mail"
        assert first["message_id"] == "<a@x>"
        for key in ("uid", "from", "to", "subject", "date", "flags"):
            assert key in first
        assert "references" not in first

    async def test_sorted_by_date_not_by_uid(self, bridge):
        bridge.add("All Mail", _msg(9, "<a@x>", "Mon, 05 Oct 2026 09:00:00 +0200"))
        # Senare UID men tidigare datum (t.ex. importerat mejl), annan tidszon
        bridge.add("All Mail", _msg(3, "<b@x>", "Mon, 05 Oct 2026 08:00:00 +0000", "<a@x>", "<a@x>"))
        _start(bridge, 70, "<a@x>")
        result = await get_thread(bridge.imap, "70", "INBOX")
        assert _uids(result) == ["9", "3"]

    async def test_unparseable_date_is_sorted_last(self, bridge):
        bridge.add("All Mail", _msg(1, "<a@x>", "inte ett datum"))
        bridge.add("All Mail", _msg(2, "<b@x>", "Mon, 05 Oct 2026 10:00:00 +0200", "<a@x>", "<a@x>"))
        _start(bridge, 70, "<b@x>")
        assert _uids(await get_thread(bridge.imap, "70", "INBOX")) == ["2", "1"]

    async def test_substring_matches_are_not_part_of_the_thread(self, bridge):
        # Servern söker delsträngar; bara exakta ID:n räknas
        bridge.add("All Mail", _msg(1, "<a@x>", "Mon, 05 Oct 2026 09:00:00 +0200"))
        bridge.add("All Mail", _msg(2, "<xa@x>", "Mon, 05 Oct 2026 10:00:00 +0200",
                                    subject="se <a@x>", References="<ba@x>"))
        _start(bridge, 70, "<a@x>")
        assert _uids(await get_thread(bridge.imap, "70", "INBOX")) == ["1"]

    async def test_max_messages_keeps_newest_and_the_start(self, bridge):
        self._fill(bridge)
        _start(bridge, 70, "<a@x>")
        result = await get_thread(bridge.imap, "70", "INBOX", max_messages=2)
        # Runda 1 hittar a, b och c (c refererar a); taket nås och sökningen stannar
        assert _uids(result) == ["1", "3"]
        assert result["complete"] is False
        assert result["total"] >= 3
        assert "max_messages" in result["note"]

    async def test_rounds_are_capped(self, bridge, monkeypatch):
        monkeypatch.setattr("protonmail_mcp.imap_threads._MAX_ROUNDS", 1)
        self._fill(bridge)
        _start(bridge, 70, "<a@x>")
        result = await get_thread(bridge.imap, "70", "INBOX")
        # Runda 1 hittar a och allt som refererar a; e (svar på c) kräver en runda till
        assert _uids(result) == ["1", "2", "3"]
        assert result["complete"] is False

    async def test_many_ids_are_split_over_several_searches(self, bridge, monkeypatch):
        monkeypatch.setattr("protonmail_mcp.imap_threads._IDS_PER_SEARCH", 2)
        self._fill(bridge)
        _start(bridge, 70, "<c@x>")
        result = await get_thread(bridge.imap, "70", "INBOX")
        assert _uids(result) == ["1", "2", "3", "5"]
        assert all(c.count("HEADER Message-ID") <= 2 for c in bridge.search_commands)

    async def test_message_without_message_id_is_returned_alone(self, bridge):
        bridge.add("All Mail", _msg(1, "<a@x>", "Mon, 05 Oct 2026 09:00:00 +0200"))
        bridge.add("INBOX", FakeMessage(uid=70, headers={"Subject": "Utan ID", "From": "a@x"}))
        result = await get_thread(bridge.imap, "70", "INBOX")
        assert _uids(result) == ["70"]
        assert result["messages"][0]["mailbox"] == "INBOX"
        assert "Message-ID" in result["note"]
        assert bridge.search_commands == []

    async def test_unknown_uid(self, bridge):
        self._fill(bridge)
        _start(bridge, 70, "<a@x>")
        with pytest.raises(ValueError, match="Inget meddelande med UID 71 i INBOX"):
            await get_thread(bridge.imap, "71", "INBOX")

    @pytest.mark.parametrize("uid", ["1:*", "1,2", "x"])
    async def test_invalid_uid_is_refused_before_bridge(self, bridge, uid):
        with pytest.raises(ValueError, match="Ogiltigt UID"):
            await get_thread(bridge.imap, uid, "INBOX")
        bridge.imap._client.select.assert_not_called()

    async def test_invalid_mailbox_is_refused_before_bridge(self, bridge):
        with pytest.raises(ValueError, match="mailbox"):
            await get_thread(bridge.imap, "1", "IN\r\nBOX")
        bridge.imap._client.select.assert_not_called()

    async def test_uses_peek_so_nothing_is_marked_read(self, bridge):
        self._fill(bridge)
        _start(bridge, 70, "<a@x>")
        await get_thread(bridge.imap, "70", "INBOX")
        calls = [str(c) for c in bridge.imap._client.fetch.call_args_list + bridge.imap._client.uid.call_args_list]
        assert calls and all("BODY.PEEK[" in c for c in calls)


class TestTool:
    def _tool(self):
        return next(t for t in mcp._tool_manager.list_tools() if t.name == "get_thread")

    def test_registered_with_required_mailbox(self):
        import protonmail_mcp.tools.threads  # noqa: F401

        params = self._tool().parameters
        assert set(params["required"]) == {"uid", "mailbox"}
        limit = params["properties"]["max_messages"]
        assert limit["minimum"] == 1 and limit["maximum"] == 200 and limit["default"] == 50

    async def test_delegates_to_imap_threads(self, monkeypatch):
        from protonmail_mcp.tools import threads

        fake = AsyncMock(return_value={"mailbox": "All Mail", "messages": [], "total": 0,
                                       "complete": True, "note": None})
        monkeypatch.setattr(threads, "fetch_thread", fake)
        ctx = MagicMock()
        await threads.get_thread(ctx, uid="5", mailbox="INBOX", max_messages=7)
        fake.assert_awaited_once_with(ctx.request_context.lifespan_context.imap, "5", "INBOX", max_messages=7)

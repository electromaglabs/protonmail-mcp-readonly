"""get_thread (efterfix-tradetikett): tak på ID:n, sökningar och tid, låset släpps mellan sökningarna,
och mailbox-fältet stämmer med uid:t."""
import asyncio

import pytest

from protonmail_mcp import imap_threads
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient, _serialized
from protonmail_mcp.imap_threads import _ids_of, _message_ids, get_thread
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


def _msg(uid, mid, date, irt="", refs=""):
    return FakeMessage(uid=uid, headers={
        "From": "a@example.com", "To": "b@example.com", "Subject": "Ämne",
        "Date": date, "Message-ID": mid, "In-Reply-To": irt, "References": refs,
    })


def _junk_start(bridge, count, parent="<b@x>", uid=9):
    refs = " ".join(f"<{i}@evil.example>" for i in range(count)) + f" {parent}"
    for box, box_uid in (("INBOX", uid), ("All Mail", 9000 + uid)):
        bridge.add(box, _msg(box_uid, "<start@evil.example>", "Thu, 08 Oct 2026 09:00:00 +0200", parent, refs))


def _thread_ab(bridge):
    bridge.add("All Mail", _msg(1, "<a@x>", "Mon, 05 Oct 2026 09:00:00 +0200"))
    bridge.add("All Mail", _msg(2, "<b@x>", "Mon, 05 Oct 2026 10:00:00 +0200", "<a@x>", "<a@x>"))


class TestIdOrder:
    def test_closest_ids_come_first(self):
        # Eget ID, In-Reply-To, roten och sedan References bakifrån (närmast först)
        meta = {"message_id": "<e@x>", "in_reply_to": "<d@x>", "references": "<a@x> <b@x> <c@x> <d@x>"}
        assert _ids_of(meta) == ["<e@x>", "<d@x>", "<a@x>", "<c@x>", "<b@x>"]

    def test_many_ids_are_extracted_quickly(self):
        refs = " ".join(f"<{i}@x>" for i in range(20000))
        assert len(_message_ids(refs)) == 20000


class TestCaps:
    async def test_junk_references_give_a_bounded_number_of_searches(self, bridge):
        _thread_ab(bridge)
        _junk_start(bridge, 5000)
        result = await get_thread(bridge.imap, "9", "INBOX")
        assert len(bridge.search_commands) == imap_threads._MAX_SEARCHES
        assert result["complete"] is False
        assert "söktes inte" in result["note"]

    async def test_max_messages_one_stops_after_the_first_hits(self, bridge):
        # Granskningens fall: max_messages=1 gav ändå 251 SEARCH
        _thread_ab(bridge)
        _junk_start(bridge, 5000)
        result = await get_thread(bridge.imap, "9", "INBOX", max_messages=1)
        assert len(bridge.search_commands) <= imap_threads._MAX_SEARCHES
        assert result["complete"] is False

    async def test_followed_ids_are_capped(self, bridge, monkeypatch):
        monkeypatch.setattr(imap_threads, "_MAX_IDS", 30)
        monkeypatch.setattr(imap_threads, "_MAX_SEARCHES", 100)
        _thread_ab(bridge)
        _junk_start(bridge, 500)
        result = await get_thread(bridge.imap, "9", "INBOX")
        searched = sum(c.count("HEADER Message-ID") for c in bridge.search_commands)
        assert searched == 30
        assert result["complete"] is False

    async def test_parent_is_found_despite_junk(self, bridge):
        _thread_ab(bridge)
        _junk_start(bridge, 5000)
        result = await get_thread(bridge.imap, "9", "INBOX")
        assert {"1", "2", "9009"} <= {m["uid"] for m in result["messages"]}

    async def test_time_budget_stops_the_search(self, bridge, monkeypatch):
        now = {"t": 0.0}
        monkeypatch.setattr(imap_threads, "_clock", lambda: now["t"])
        original = bridge._search

        async def slow(*args, **kwargs):
            now["t"] += 25
            return await original(*args, **kwargs)

        bridge.imap._client.search.side_effect = slow
        _thread_ab(bridge)
        _junk_start(bridge, 5000)
        result = await get_thread(bridge.imap, "9", "INBOX")
        assert len(bridge.search_commands) == 3  # 0 → 25 → 50 → 75 s; budgeten är 60 s
        assert result["complete"] is False
        assert "tidsgränsen" in result["note"]

    async def test_ordinary_thread_is_unaffected(self, bridge):
        _thread_ab(bridge)
        bridge.add("INBOX", _msg(7, "<b@x>", "Mon, 05 Oct 2026 10:00:00 +0200", "<a@x>", "<a@x>"))
        result = await get_thread(bridge.imap, "7", "INBOX")
        assert [m["uid"] for m in result["messages"]] == ["1", "2"]
        assert result["complete"] is True and result["note"] is None


class TestLock:
    async def test_other_calls_run_between_searches(self, bridge):
        _thread_ab(bridge)
        _junk_start(bridge, 200)
        events: list[str] = []

        @_serialized
        async def other_call(_imap):
            events.append("annat")

        original = bridge._search
        started: list = []

        async def search(*args, **kwargs):
            events.append("sök")
            if not started:
                started.append(asyncio.ensure_future(other_call(bridge.imap)))
                await asyncio.sleep(0)
            return await original(*args, **kwargs)

        bridge.imap._client.search.side_effect = search
        await get_thread(bridge.imap, "9", "INBOX")
        await asyncio.gather(*started)
        assert events.count("sök") >= 2
        assert events.index("annat") < events.index("sök", 1), events

    async def test_mail_view_is_reselected_after_a_pause(self, bridge):
        # Ett annat anrop kan ha valt en annan mapp mellan sökningarna
        _thread_ab(bridge)
        _junk_start(bridge, 200)
        original_search, original_fetch = bridge._search, bridge._fetch
        searches = []

        async def search(*args, **kwargs):
            searches.append(bridge.selected)
            return await original_search(*args, **kwargs)

        async def fetch(*args, **kwargs):
            result = await original_fetch(*args, **kwargs)
            bridge.selected = "INBOX"  # som om ett annat verktyg valt INBOX efteråt
            return result

        bridge.imap._client.search.side_effect = search
        bridge.imap._client.fetch.side_effect = fetch
        result = await get_thread(bridge.imap, "9", "INBOX")
        assert len(searches) >= 2 and set(searches) == {"All Mail"}
        assert "2" in [m["uid"] for m in result["messages"]]


class TestMailboxField:
    async def test_without_message_id_the_uid_belongs_to_the_source_mailbox(self, bridge):
        bridge.add("All Mail", _msg(70, "<a@x>", "Mon, 05 Oct 2026 09:00:00 +0200"))
        bridge.add("INBOX", FakeMessage(uid=70, headers={"Subject": "Utan ID", "From": "a@x"}))
        result = await get_thread(bridge.imap, "70", "INBOX")
        assert result["mailbox"] == "INBOX"
        assert [(m["uid"], m["mailbox"]) for m in result["messages"]] == [("70", "INBOX")]
        assert 'mailbox="INBOX"' in result["note"]

    async def test_every_message_mailbox_matches_the_top_level(self, bridge):
        _thread_ab(bridge)
        bridge.add("INBOX", _msg(7, "<b@x>", "Mon, 05 Oct 2026 10:00:00 +0200", "<a@x>", "<a@x>"))
        result = await get_thread(bridge.imap, "7", "INBOX")
        assert {m["mailbox"] for m in result["messages"]} == {result["mailbox"]} == {"All Mail"}

    def test_tool_docstring_does_not_promise_all_mail_always(self):
        from protonmail_mcp.tools.threads import get_thread as tool

        doc = tool.__doc__
        assert 'get_email(uid, mailbox="All Mail")' not in doc
        assert "mejlets eget mailbox-fält" in doc
        assert "saknar Message-ID" in doc

    def test_module_docstring_does_not_promise_all_mail_always(self):
        assert 'mailbox ("All Mail")' not in get_thread.__doc__

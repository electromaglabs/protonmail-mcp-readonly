"""BDD: get_thread har tak på sökningar och tid, och släpper anslutningen mellan sökningarna."""
import asyncio

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import imap_threads
from protonmail_mcp.imap_client import _serialized
from tests.feat_sok_fakebridge import FakeMessage

scenarios("efterfix_tradetikett_trad.feature")


@pytest.fixture
def clock(monkeypatch):
    """Låtsasklocka för imap_threads; sökningar kan ställa fram den."""
    state = {"now": 0.0}
    monkeypatch.setattr(imap_threads, "_clock", lambda: state["now"])
    return state


@given(parsers.parse(
    'ett mejl i INBOX och All Mail med UID "{uid:d}" som svarar på "{parent}" '
    "och har {count:d} påhittade ID:n i References"
))
def message_with_junk_references(bridge, uid, parent, count):
    # Det riktiga föräldra-ID:t står sist, som i ett vanligt svar
    refs = " ".join(f"<{i}@evil.example>" for i in range(count)) + f" {parent}"
    headers = {
        "From": "x@evil.example", "To": "me@proton.me", "Subject": "Re: Offert",
        "Date": "Thu, 08 Oct 2026 09:00:00 +0200", "Message-ID": "<start@evil.example>",
        "In-Reply-To": parent, "References": refs,
    }
    bridge.add("INBOX", FakeMessage(uid=uid, headers=dict(headers)))
    bridge.add("All Mail", FakeMessage(uid=9000 + uid, headers=dict(headers)))


def _client(mock_ctx):
    return mock_ctx.request_context.lifespan_context.imap._client


@given(parsers.parse("att varje sökning i All Mail tar {seconds:d} sekunder"))
def slow_search(mock_ctx, bridge, clock, seconds):
    async def slow(*args, **kwargs):
        clock["now"] += seconds
        return await bridge._search(*args, **kwargs)

    _client(mock_ctx).search.side_effect = slow


@when(parsers.parse(
    'jag hämtar konversationen för UID "{uid}" i INBOX medan ett annat verktygsanrop väntar på anslutningen'
))
def fetch_thread_with_other_call(mock_ctx, bridge, outcome, uid):
    from protonmail_mcp.tools.threads import get_thread

    imap = mock_ctx.request_context.lifespan_context.imap
    events: list[str] = []
    outcome["events"] = events

    @_serialized
    async def other_call(_imap):
        events.append("annat anrop")

    original = bridge._search
    started: list = []

    async def search(*args, **kwargs):
        events.append("sökning")
        if not started:
            # Ett annat verktygsanrop kommer in medan första sökningen pågår
            started.append(asyncio.ensure_future(other_call(imap)))
            await asyncio.sleep(0)
        return await original(*args, **kwargs)

    _client(mock_ctx).search.side_effect = search

    async def run():
        result = await get_thread(mock_ctx, uid=uid, mailbox="INBOX")
        await asyncio.gather(*started)
        return result

    outcome["result"] = asyncio.run(run())


@then(parsers.parse("ska Bridge ha fått högst {count:d} sökningar"))
def at_most_searches(bridge, count):
    assert 0 < len(bridge.search_commands) <= count, len(bridge.search_commands)


@then(parsers.parse('ska anteckningen nämna "{text}"'))
def note_mentions(outcome, text):
    assert text in (outcome["result"]["note"] or ""), outcome["result"]["note"]


@then(parsers.parse('ska konversationen innehålla All Mail-UID "{uid}"'))
def thread_contains(outcome, uid):
    assert "error" not in outcome, outcome.get("error")
    assert uid in [m["uid"] for m in outcome["result"]["messages"]]


@then("ska det andra anropet ha körts före konversationens andra sökning")
def other_call_ran_between(outcome):
    events = outcome["events"]
    assert events.count("sökning") >= 2, events
    assert events.index("annat anrop") < events.index("sökning", 1), events


@then(parsers.parse('ska konversationen bestå av UID "{uids}"'))
def thread_has_uids(outcome, uids):
    assert "error" not in outcome, outcome.get("error")
    assert [m["uid"] for m in outcome["result"]["messages"]] == [u.strip() for u in uids.split(",")]


@then("ska beskrivningen av get_thread hänvisa till varje mejls mailbox-fält")
def docstring_points_to_each_mailbox():
    from protonmail_mcp.tools.threads import get_thread

    doc = get_thread.__doc__
    assert 'get_email(uid, mailbox="All Mail")' not in doc
    assert "mejlets eget mailbox-fält" in doc

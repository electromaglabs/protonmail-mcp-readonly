"""Gemensamma steg för verktygsscenarierna för nya mejl (ny-mejl).

Verktygen körs med en riktig delad IMAPClient och en riktig MailWatcher mot
låtsas-Bridgen i tests/ny_mejl_fakeidle.py.
"""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, parsers, then, when

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.imap_idle import MailWatcher
from protonmail_mcp.server import AppContext
from protonmail_mcp.tools import new_mail
from protonmail_mcp.tools.messages import list_emails
from tests.llm_kontrakt_support import client_session, text_of
from tests.ny_mejl_fakeidle import FakeIdleBridge

@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(new_mail, "POLL_INTERVAL", 0.1)
    loop = asyncio.new_event_loop()
    e = SimpleNamespace(loop=loop, fake=None, app=None, ctx=None, result=None, elapsed=None,
                        list_done_at=None, wait_done_at=None, monkeypatch=monkeypatch)
    yield e
    if e.app is not None:
        loop.run_until_complete(e.app.watcher.stop())
        loop.run_until_complete(e.app.imap.disconnect())
    if e.fake is not None:
        loop.run_until_complete(e.fake.stop())
    loop.close()


def run(env, coro):
    return env.loop.run_until_complete(asyncio.wait_for(coro, 15))


def eventually(env, predicate, timeout=5.0):
    async def wait():
        deadline = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < deadline, "villkoret uppfylldes inte"
            await asyncio.sleep(0.01)

    run(env, wait())


def _app(env, enabled):
    settings = Settings(username="u", password="p", imap_port=env.fake.port, imap_timeout=2,
                        watch_enabled=enabled, _env_file=None)

    async def make():
        watcher = MailWatcher(settings)
        watcher.start()
        return AppContext(imap=IMAPClient(settings), smtp=None, watcher=watcher)

    env.app = run(env, make())
    env.ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=env.app))


@given("en Bridge med IDLE där INBOX har mejlen 1, 2 och 3")
def bridge(env):
    env.fake = FakeIdleBridge()
    env.fake.add_box("INBOX", [1, 2, 3])
    env.fake.add_box("Folders/Kunder", [7])
    run(env, env.fake.start())


@given("att servern bevakar INBOX")
def watching(env):
    _app(env, enabled=True)
    eventually(env, lambda: env.app.watcher.is_watching("INBOX"))


@given("att bevakningen är avstängd")
def not_watching(env):
    _app(env, enabled=False)


@when(parsers.parse('ett mejl med ämnet "{subject}" kommer till INBOX och bevakningen har sett det'))
def deliver_seen(env, subject):
    uid = env.fake.deliver("INBOX", subject=subject)
    eventually(env, lambda: str(uid) in [m["uid"] for m in env.app.watcher.recent_events("INBOX")])


@when(parsers.parse('ett mejl med ämnet "{subject}" kommer till INBOX'))
def deliver(env, subject):
    env.fake.deliver("INBOX", subject=subject)


@when("jag anropar check_new_emails för INBOX")
def check(env):
    env.result = run(env, new_mail.check_new_emails(env.ctx, mailbox="INBOX"))


@when(parsers.parse('jag anropar check_new_emails för INBOX med since_uid "{uid}"'))
def check_since(env, uid):
    env.result = run(env, new_mail.check_new_emails(env.ctx, mailbox="INBOX", since_uid=uid))


@when(parsers.parse(
    'jag väntar på nya mejl i INBOX i högst {timeout:d} sekunder och ett mejl med ämnet "{subject}" '
    "kommer efter {delay:f} sekunder"
))
def wait_with_mail(env, timeout, subject, delay):
    async def scenario():
        async def later():
            await asyncio.sleep(delay)
            env.fake.deliver("INBOX", subject=subject)

        task = asyncio.create_task(later())
        begin = time.monotonic()
        env.result = await new_mail.wait_for_new_email(env.ctx, mailbox="INBOX", timeout_seconds=timeout)
        env.elapsed = time.monotonic() - begin
        await task

    run(env, scenario())


@when(parsers.parse("jag väntar på nya mejl i INBOX i högst {timeout:d} sekunder"))
def wait_plain(env, timeout):
    begin = time.monotonic()
    env.result = run(env, new_mail.wait_for_new_email(env.ctx, mailbox="INBOX", timeout_seconds=timeout))
    env.elapsed = time.monotonic() - begin


@when(parsers.parse("jag väntar på nya mejl i INBOX i högst {timeout:d} sekunder och listar INBOX under tiden"))
def wait_and_list(env, timeout):
    async def scenario():
        async def waiter():
            env.result = await new_mail.wait_for_new_email(env.ctx, mailbox="INBOX", timeout_seconds=timeout)
            env.wait_done_at = time.monotonic()

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0.3)
        listing = await asyncio.wait_for(list_emails(env.ctx, mailbox="INBOX"), 2)
        env.list_done_at = time.monotonic()
        assert [m["uid"] for m in listing["messages"]] == ["3", "2", "1"]
        await task

    run(env, scenario())


@when(parsers.parse("jag anropar wait_for_new_email med timeout_seconds {timeout:d}"))
def call_out_of_range(env, timeout):
    env.imap_mock = AsyncMock()
    from protonmail_mcp import config

    settings = Settings(username="u", password="p", _env_file=None)
    env.monkeypatch.setattr(config, "get_settings", lambda: settings)

    async def call():
        async with client_session(env.monkeypatch, imap=env.imap_mock) as session:
            return await session.call_tool("wait_for_new_email", {"timeout_seconds": timeout})

    env.result = run(env, call())


def _uids(env):
    return [m["uid"] for m in env.result["messages"]]


@then(parsers.parse('ska svaret innehålla UID:n "{uids}" med mailbox "{mailbox}"'))
def has_uids(env, uids, mailbox):
    assert _uids(env) == uids.split(","), env.result
    assert all(m["mailbox"] == mailbox for m in env.result["messages"])
    assert env.result["mailbox"] == mailbox
    for m in env.result["messages"]:
        assert {"uid", "mailbox", "from", "to", "subject", "date", "message_id", "flags"} <= set(m)


@then("ska svaret inte innehålla några mejl")
def no_messages(env):
    assert env.result["messages"] == [], env.result


@then("ska svaret säga att INBOX bevakas")
def says_watching(env):
    assert env.result["watching"] is True
    assert env.result["source"] == "watcher"


@then("ska svaret säga att INBOX inte bevakas")
def says_not_watching(env):
    assert env.result["watching"] is False
    assert env.result["source"] == "imap"


@then("ska svaret ha tiden för senaste händelsen")
def has_last_event(env):
    assert env.result["last_event"] and "T" in env.result["last_event"]


@then(parsers.parse('ska anteckningen nämna "{text}"'))
def note_mentions(env, text):
    assert text in (env.result["note"] or ""), env.result


@then("ska Bridge bara ha fått hämtningar med BODY.PEEK")
def only_peek(env):
    fetches = env.fake.fetch_lines()
    assert fetches
    for line in fetches:
        assert "BODY[" not in line.upper() or "BODY.PEEK[" in line.upper(), line


@then("ska inget mejl i INBOX vara markerat som läst")
def none_read(env):
    assert all("\\Seen" not in m.flags for m in env.fake.boxes["INBOX"].messages)


@then("ska väntan inte ha gått ut")
def not_timed_out(env):
    assert env.result["timed_out"] is False


@then("ska väntan ha gått ut")
def timed_out(env):
    assert env.result["timed_out"] is True


@then(parsers.parse("ska väntan ha tagit under {seconds:d} sekunder"))
def quick(env, seconds):
    assert env.elapsed < seconds


@then("ska listningen ha blivit klar medan väntan pågick")
def listed_during_wait(env):
    assert env.list_done_at < env.wait_done_at - 1
    assert env.result["timed_out"] is True


@then("ska anropet avvisas utan att Bridge kontaktas")
def rejected(env):
    assert env.result.isError
    assert "timeout_seconds" in text_of(env.result)
    # client_session gör bool(imap); inga andra anrop får ha skett
    assert [c for c in env.imap_mock.mock_calls if c[0] != "__bool__"] == []

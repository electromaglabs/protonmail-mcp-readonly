"""Gemensamma steg för efterfix-idle-scenarierna (bevakningen av nya mejl).

Scenarierna kör den riktiga MailWatcher, de riktiga verktygen och den riktiga
IMAPClient (med aioimaplib) mot låtsas-Bridgen i tests/ny_mejl_fakeidle.py,
som köar EXISTS och svarar NO på en UID-sökning i en tom mapp som Bridge gör.
"""
import asyncio
import time
from types import SimpleNamespace

import pytest
from pytest_bdd import given, parsers, then, when

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.imap_idle import MailWatcher
from protonmail_mcp.server import AppContext
from protonmail_mcp.tools import new_mail
from tests.ny_mejl_fakeidle import FakeIdleBridge


@pytest.fixture
def env(monkeypatch):
    loop = asyncio.new_event_loop()
    e = SimpleNamespace(loop=loop, fake=None, port=None, watcher=None, app=None, ctx=None,
                        received=[], delays=[], result=None, error=None, elapsed=None,
                        monkeypatch=monkeypatch, cleanups=[])
    yield e
    for cleanup in e.cleanups:
        loop.run_until_complete(cleanup())
    if e.app is not None:
        loop.run_until_complete(e.app.imap.disconnect())
    if e.watcher is not None:
        loop.run_until_complete(e.watcher.stop())
    if e.fake is not None:
        loop.run_until_complete(e.fake.stop())
    loop.close()


def run(env, coro, timeout=15):
    return env.loop.run_until_complete(asyncio.wait_for(coro, timeout))


def eventually(env, predicate, timeout=5.0, what="villkoret"):
    async def wait():
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise AssertionError(f"{what} uppfylldes inte inom {timeout} s")
            await asyncio.sleep(0.01)

    run(env, wait(), timeout + 5)


def settings(env, **kw):
    kw.setdefault("imap_timeout", 2)
    return Settings(username="u", password="p", imap_port=env.port, _env_file=None, **kw)


def start_watcher(env, mailboxes="INBOX", settings_kw=None, **kw):
    s = settings(env, watch_mailboxes=mailboxes, **(settings_kw or {}))

    async def record_sleep(delay):
        env.delays.append(delay)
        await asyncio.sleep(0)

    kw.setdefault("sleep", record_sleep)
    env.watcher = MailWatcher(s, **kw)

    async def listener(mailbox, messages):
        env.received.append((mailbox, messages))

    env.watcher.add_listener(listener)
    env.app = AppContext(imap=IMAPClient(s), smtp=None, watcher=env.watcher)
    env.ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=env.app))

    async def start():
        env.watcher.start()

    run(env, start())


def wait_watching(env, mailbox="INBOX"):
    eventually(env, lambda: env.watcher.is_watching(mailbox), what=f"bevakningen av {mailbox}")


def queue_uids(env, mailbox="INBOX"):
    return sorted(int(m["uid"]) for m in env.watcher.recent_events(mailbox))


@given("en Bridge med IDLE där INBOX har mejlen 1, 2 och 3")
def bridge(env):
    env.fake = FakeIdleBridge()
    env.fake.add_box("INBOX", [1, 2, 3])
    env.port = run(env, env.fake.start())


@given(parsers.parse("att bevakningen av INBOX har startat med förnyelse var {seconds:f} sekunder"))
def watching_with_renewal(env, seconds):
    start_watcher(env, renew_seconds=seconds)
    wait_watching(env)


@then(parsers.parse('ska händelsekön för INBOX inom {seconds:f} sekunder innehålla UID:n "{uids}"'))
def queue_has_within(env, seconds, uids):
    wanted = [int(u) for u in uids.split(",")]
    eventually(env, lambda: queue_uids(env) == wanted, timeout=seconds, what=f"händelsekön {wanted}")


@given("att check_new_emails har anropats för INBOX")
def checked_once(env):
    run(env, new_mail.check_new_emails(env.ctx, mailbox="INBOX"))


@when("jag anropar check_new_emails för INBOX")
def check(env):
    env.error = None
    try:
        env.result = run(env, new_mail.check_new_emails(env.ctx, mailbox="INBOX"))
    except Exception as exc:  # noqa: BLE001 — scenariot kontrollerar felet
        env.error = exc


@when(parsers.parse("det har gått {seconds:f} sekunder"))
def time_passes(env, seconds):
    run(env, asyncio.sleep(seconds))


@then(parsers.parse('ska svaret innehålla UID:n "{uids}"'))
def has_uids(env, uids):
    assert env.error is None, env.error
    assert [m["uid"] for m in env.result["messages"]] == uids.split(","), env.result


@then("ska svaret inte innehålla några mejl")
def no_messages(env):
    assert env.error is None, env.error
    assert env.result["messages"] == [], env.result


@then(parsers.parse('ska anteckningen nämna "{text}"'))
def note_mentions(env, text):
    assert text in (env.result["note"] or ""), env.result

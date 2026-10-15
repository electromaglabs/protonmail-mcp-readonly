"""BDD: bevakningen av nya mejl med IMAP IDLE (ny-mejl).

Scenarierna kör den riktiga MailWatcher (och därmed riktiga IMAPClient och
aioimaplib) mot låtsas-Bridgen i tests/ny_mejl_fakeidle.py på en slumpport.
"""
import asyncio
import socket
import time
from types import SimpleNamespace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.imap_idle import MailWatcher
from tests.ny_mejl_fakeidle import FakeIdleBridge

scenarios("ny_mejl_bevakning.feature")


@pytest.fixture
def env():
    loop = asyncio.new_event_loop()
    e = SimpleNamespace(loop=loop, fake=None, port=None, watcher=None, received=[], delays=[],
                        shared=None, start_time=None)
    yield e
    if e.watcher is not None:
        loop.run_until_complete(e.watcher.stop())
    if e.fake is not None:
        loop.run_until_complete(e.fake.stop())
    loop.close()


def run(env, coro):
    return env.loop.run_until_complete(asyncio.wait_for(coro, 10))


def eventually(env, predicate, timeout=5.0, what="villkoret"):
    async def wait():
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise AssertionError(f"{what} uppfylldes inte inom {timeout} s")
            await asyncio.sleep(0.01)

    run(env, wait())


def _settings(port, **kw):
    return Settings(username="u", password="p", imap_port=port, imap_timeout=2, _env_file=None, **kw)


def _start_watcher(env, mailboxes="INBOX", **kw):
    settings = _settings(env.port, watch_mailboxes=mailboxes, **kw.pop("settings", {}))

    async def record_sleep(delay):
        env.delays.append(delay)
        await asyncio.sleep(0)

    kw.setdefault("sleep", record_sleep)
    env.watcher = MailWatcher(settings, **kw)

    async def listener(mailbox, messages):
        env.received.append((mailbox, messages))

    env.watcher.add_listener(listener)

    async def start():
        begin = time.monotonic()
        env.watcher.start()
        env.start_time = time.monotonic() - begin

    run(env, start())


def _wait_watching(env, mailbox="INBOX"):
    eventually(env, lambda: env.watcher.is_watching(mailbox), what=f"bevakningen av {mailbox}")


def _received_uids(env):
    return [m["uid"] for _, batch in env.received for m in batch]


# --- Givet --------------------------------------------------------------------

@given("en Bridge med IDLE där INBOX har mejlen 1, 2 och 3")
def bridge(env):
    env.fake = FakeIdleBridge()
    env.fake.add_box("INBOX", [1, 2, 3])
    env.fake.add_box("Folders/Kunder", [7])
    env.port = run(env, env.fake.start())


@given("en Bridge som inte går att nå")
def unreachable(env):
    run(env, env.fake.stop())
    env.fake = None
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        env.port = s.getsockname()[1]  # stängs direkt: ingen lyssnar på porten


@given("att bevakningen av INBOX har startat")
def watching(env):
    _start_watcher(env)
    _wait_watching(env)


@given(parsers.parse("att bevakningen av INBOX har startat med förnyelse var {seconds:f} sekund"))
def watching_with_renewal(env, seconds):
    _start_watcher(env, renew_seconds=seconds)
    _wait_watching(env)


@given("att bevakningen av INBOX har startat med en lyssnare som kastar ett fel")
def watching_with_bad_listener(env):
    _start_watcher(env)

    async def broken(mailbox, messages):
        raise RuntimeError("lyssnaren gick sönder")

    # Den trasiga lyssnaren först, så att den andra måste anropas ändå
    env.watcher._listeners.insert(0, broken)
    _wait_watching(env)


@given('att INBOX och "Folders/Kunder" bevakas')
def watching_two(env):
    _start_watcher(env, mailboxes="INBOX,Folders/Kunder")
    _wait_watching(env, "INBOX")
    _wait_watching(env, "Folders/Kunder")


# --- När ----------------------------------------------------------------------

@when(parsers.parse('ett mejl med ämnet "{subject}" kommer till INBOX'))
def deliver(env, subject):
    env.fake.deliver("INBOX", subject=subject)


@when(parsers.parse("det har gått {seconds:f} sekunder"))
def time_passes(env, seconds):
    run(env, asyncio.sleep(seconds))


@when(parsers.parse('Bridge startas om och ett mejl med ämnet "{subject}" kommer under tiden'))
def restart_with_mail(env, subject):
    before = env.fake.connections_total
    run(env, env.fake.drop_all())
    env.fake.deliver("INBOX", subject=subject)
    env.connections_before_restart = before


@when("Bridge startas om")
def restart(env):
    env.connections_before_restart = env.fake.connections_total
    run(env, env.fake.drop_all())


@when(parsers.parse("Bridge byter UIDVALIDITY för INBOX och numrerar om mejlen till 1 och 2"))
def renumber(env):
    env.fake.renumber("INBOX", uidvalidity=99, uids=[1, 2])


@when(parsers.parse(
    "bevakningen av INBOX startas med väntetiden {initial:d} sekund och taket {cap:d} sekunder"
))
def start_with_backoff(env, initial, cap):
    _start_watcher(env, backoff_initial=float(initial), backoff_max=float(cap))


@when("bevakningen av INBOX startas")
def start_unreachable(env):
    async def slow_sleep(delay):
        env.delays.append(delay)
        await asyncio.sleep(1)

    _start_watcher(env, sleep=slow_sleep)


@when("bevakningen startas med PROTONMAIL_WATCH_ENABLED=false")
def start_disabled(env):
    _start_watcher(env, settings={"watch_enabled": False})
    run(env, asyncio.sleep(0.2))


@when("bevakningen stoppas")
def stop(env):
    env.tasks_before_stop = list(env.watcher._tasks.values())
    run(env, env.watcher.stop())


# --- Så -----------------------------------------------------------------------

@then(parsers.parse('ska lyssnaren ha fått mejlet med UID {uid} i INBOX med ämnet "{subject}"'))
def listener_got(env, uid, subject):
    eventually(env, lambda: uid in _received_uids(env), what=f"lyssnaranropet för UID {uid}")
    for mailbox, batch in env.received:
        for m in batch:
            if m["uid"] == uid:
                assert mailbox == "INBOX"
                assert m["mailbox"] == "INBOX"
                assert m["subject"] == subject
                assert m["from"] == "anna@example.com"
                assert {"uid", "mailbox", "from", "to", "subject", "date", "flags"} <= set(m)


@then(parsers.parse("ska lyssnaren bara ha fått UID {uid}"))
def listener_only(env, uid):
    eventually(env, lambda: uid in _received_uids(env))
    run(env, asyncio.sleep(0.1))
    assert _received_uids(env) == [uid]


@then(parsers.parse("ska händelsekön för INBOX innehålla UID {uid}"))
def queue_has(env, uid):
    assert uid in [m["uid"] for m in env.watcher.recent_events("INBOX")]


@then("ska Bridge bara ha fått hämtningar med BODY.PEEK")
def only_peek(env):
    fetches = env.fake.fetch_lines()
    assert fetches, "ingen hämtning gjordes"
    for line in fetches:
        assert "BODY[" not in line.upper() or "BODY.PEEK[" in line.upper(), line


@then(parsers.parse("ska mejlet med UID {uid:d} fortfarande vara oläst"))
def still_unread(env, uid):
    msg = next(m for m in env.fake.boxes["INBOX"].messages if m.uid == uid)
    assert "\\Seen" not in msg.flags


@then("ska bevakningen ha en egen anslutning till Bridge")
def own_connection(env):
    assert env.fake.connections_total == 1
    assert env.fake.open_connections == 1


@then("ska verktygens delade anslutning inte ha använts")
def shared_not_used(env):
    # MailWatcher tar bara inställningarna — den kan inte nå verktygens IMAPClient
    shared = IMAPClient(_settings(env.port))
    assert shared._client is None
    assert not hasattr(env.watcher, "imap")


@then(parsers.parse("ska Bridge ha fått minst {count:d} IDLE på samma anslutning"))
def renewed(env, count):
    assert env.fake.connections_total == 1, "förnyelsen ska inte kräva ny anslutning"
    assert env.fake.idle_count(conn=1) >= count
    # Varje IDLE avslutades med DONE innan nästa skickades
    lines = [line for _, line in env.fake.commands]
    idles = [i for i, line in enumerate(lines) if line.split(" ")[1:2] == ["IDLE"]]
    for a, b in zip(idles, idles[1:]):
        assert "DONE" in lines[a + 1:b]


@then("ska bevakningen fortfarande bevaka INBOX")
def still_watching(env):
    assert env.watcher.is_watching("INBOX")


@then("ska bevakningen ha återanslutit")
def reconnected(env):
    eventually(env, lambda: env.fake.connections_total > env.connections_before_restart
               and env.watcher.is_watching("INBOX"), what="återanslutningen")


@then(parsers.parse("ska väntetiderna mellan försöken börja med {delays} sekunder"))
def backoff(env, delays):
    expected = [float(d) for d in delays.split(", ")]
    eventually(env, lambda: len(env.delays) >= len(expected), what="försöken")
    assert env.delays[:len(expected)] == expected


@then("ska start ha returnerat direkt")
def started_fast(env):
    assert env.start_time < 0.05


@then("ska bevakningen inte bevaka INBOX just nu")
def not_watching(env):
    eventually(env, lambda: env.watcher.status("INBOX")["last_error"] is not None, what="ett felförsök")
    status = env.watcher.status("INBOX")
    assert status["watching"] is False
    assert "Bridge" in status["last_error"]


@then("ska Bridge inte ha fått någon anslutning")
def no_connection(env):
    assert env.fake.connections_total == 0
    assert env.watcher.is_watching("INBOX") is False


@then("ska inga bevakningsuppgifter vara kvar")
def no_tasks(env):
    assert len(env.tasks_before_stop) == 2
    assert all(t.done() for t in env.tasks_before_stop)
    assert env.watcher._tasks == {}
    leftovers = [t for t in asyncio.all_tasks(env.loop) if "protonmail-watch" in t.get_name()]
    assert leftovers == []


@then("ska Bridge inte ha några öppna anslutningar")
def no_open(env):
    eventually(env, lambda: env.fake.open_connections == 0, what="att anslutningarna stängts")

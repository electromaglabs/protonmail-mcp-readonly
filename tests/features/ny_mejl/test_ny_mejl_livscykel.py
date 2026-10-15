"""BDD: bevakningen startas och stoppas i serverns lifespan (ny-mejl)."""
import asyncio
import socket
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pytest_bdd import given, scenarios, then, when

from protonmail_mcp import config
from protonmail_mcp.config import Settings
from protonmail_mcp.server import lifespan, mcp
from tests.ny_mejl_fakeidle import FakeIdleBridge

scenarios("ny_mejl_livscykel.feature")


@pytest.fixture
def env(tmp_path):
    loop = asyncio.new_event_loop()
    e = SimpleNamespace(loop=loop, fake=None, port=None, overrides={}, cm=None, app=None,
                        elapsed=None, tmp=tmp_path)
    yield e
    if e.cm is not None:
        loop.run_until_complete(e.cm.__aexit__(None, None, None))
    if e.fake is not None:
        loop.run_until_complete(e.fake.stop())
    loop.close()


def run(env, coro):
    return env.loop.run_until_complete(asyncio.wait_for(coro, 10))


def eventually(env, predicate, timeout=5.0):
    async def wait():
        deadline = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < deadline, "villkoret uppfylldes inte"
            await asyncio.sleep(0.01)

    run(env, wait())


@given("att Bridge inte går att nå")
def unreachable(env):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        env.port = s.getsockname()[1]


@given("en Bridge med IDLE där INBOX har mejlen 1, 2 och 3")
def bridge(env):
    env.fake = FakeIdleBridge()
    env.fake.add_box("INBOX", [1, 2, 3])
    env.port = run(env, env.fake.start())


@given("att PROTONMAIL_WATCH_ENABLED är false")
def disabled(env):
    env.overrides["watch_enabled"] = False


@when("servern startar")
def server_starts(env):
    settings = Settings(username="u", password="p", imap_port=env.port, imap_timeout=2,
                        attachment_dir=env.tmp / "bilagor", _env_file=None, **env.overrides)

    async def enter():
        with patch.object(config, "get_settings", return_value=settings):
            env.cm = lifespan(mcp)
            begin = time.monotonic()
            env.app = await env.cm.__aenter__()
            env.elapsed = time.monotonic() - begin

    run(env, enter())


@when("servern stängs")
def server_stops(env):
    env.tasks = list(env.app.watcher._tasks.values())
    cm, env.cm = env.cm, None
    run(env, cm.__aexit__(None, None, None))


@then("ska uppstarten ha gått på under en halv sekund")
def fast(env):
    assert env.elapsed < 0.5


@then("ska sessionen ha en bevakning av INBOX som inte är ansluten")
def watcher_not_connected(env):
    assert env.app.watcher.mailboxes == ["INBOX"]
    assert env.app.watcher.is_watching("INBOX") is False


@then("ska bevakningen av INBOX ansluta")
def connects(env):
    eventually(env, lambda: env.app.watcher.is_watching("INBOX"))


@then("ska inga bevakningsuppgifter vara kvar")
def no_tasks(env):
    assert env.tasks and all(t.done() for t in env.tasks)
    assert not [t for t in asyncio.all_tasks(env.loop) if "protonmail-watch" in t.get_name()]


@then("ska Bridge inte ha några öppna anslutningar")
def closed(env):
    eventually(env, lambda: env.fake.open_connections == 0)


@then("ska sessionen ha en bevakning som är avstängd")
def watcher_disabled(env):
    assert env.app.watcher.enabled is False
    assert env.app.watcher._tasks == {}


@then("ska Bridge inte ha fått någon anslutning")
def no_connection(env):
    run(env, asyncio.sleep(0.1))
    assert env.fake.connections_total == 0

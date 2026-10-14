"""BDD: ett avbrott mitt i ett anrop ger ConnectionError direkt (K4)."""
import asyncio
import time
from types import SimpleNamespace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from tests.efterfix_imap_avbrott import DroppingBridge

scenarios("efterfix_imap_avbrott.feature")


@pytest.fixture
def env():
    loop = asyncio.new_event_loop()
    e = SimpleNamespace(loop=loop, fake=None, client=None, results=[], errors=[], elapsed=None)
    yield e
    if e.client is not None:
        loop.run_until_complete(e.client.disconnect())
    if e.fake is not None:
        loop.run_until_complete(e.fake.stop())
    loop.close()


def _start(env, command, when_):
    env.fake = DroppingBridge(command, when_)
    env.loop.run_until_complete(env.fake.start())


@given(parsers.parse('en Bridge som stänger anslutningen efter svaret på "{command}"'))
def drops_after(env, command):
    _start(env, command, "after")


@given(parsers.parse('en Bridge som stänger anslutningen i stället för att svara på "{command}"'))
def drops_instead(env, command):
    _start(env, command, "instead")


def _client(env, timeout):
    if env.client is None:
        env.client = IMAPClient(Settings(
            username="u", password="p", imap_port=env.fake.port, imap_timeout=timeout, _env_file=None,
        ))
    return env.client


def _attempt(env, coro):
    start = time.monotonic()
    try:
        env.results.append(env.loop.run_until_complete(asyncio.wait_for(coro, 30)))
    except Exception as exc:  # noqa: BLE001 — scenariot kontrollerar felet
        env.errors.append(exc)
    env.elapsed = time.monotonic() - start


@when(parsers.parse("jag söker efter olästa mejl med timeouten {timeout:d} sekunder"))
@when(parsers.parse("jag söker efter olästa mejl med timeouten {timeout:d} sekunder igen"))
def search(env, timeout):
    _attempt(env, _client(env, timeout).search_messages("INBOX", unseen=True))


@when(parsers.parse("jag markerar mejl {uid} som läst med timeouten {timeout:d} sekunder"))
def mark_read(env, uid, timeout):
    _attempt(env, _client(env, timeout).set_flags("INBOX", uid, r"(\Seen)", add=True))


@then("ska jag få ett fel som säger att anslutningen bröts")
def connection_lost_error(env):
    assert len(env.errors) == 1, env.errors
    assert isinstance(env.errors[0], ConnectionError), repr(env.errors[0])
    assert "bröts" in str(env.errors[0])


@then(parsers.parse("ska felet komma inom {seconds:d} sekund"))
def fast(env, seconds):
    assert env.elapsed < seconds, env.elapsed


@then(parsers.parse("ska den andra sökningen ge {count:d} träffar"))
def second_ok(env, count):
    assert len(env.results) == 1, (env.results, env.errors)
    assert env.results[0]["total"] == count

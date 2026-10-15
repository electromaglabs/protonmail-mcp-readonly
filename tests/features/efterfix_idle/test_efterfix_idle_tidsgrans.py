"""BDD: wait_for_new_email:s tidsgräns när Bridge hänger (G4I-5)."""
import asyncio
import time

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools import new_mail
from tests.features.efterfix_idle.conftest import run, start_watcher

scenarios("efterfix_idle_tidsgrans.feature")


@given("en Bridge som tar emot anslutningar men aldrig svarar")
def silent_bridge(env):
    async def handle(reader, writer):
        try:
            await reader.read()  # svarar aldrig
        finally:
            writer.close()

    async def start():
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        return server, server.sockets[0].getsockname()[1]

    server, env.port = run(env, start())

    async def stop():
        server.close()

    env.cleanups.append(stop)


@given(parsers.parse("att bevakningen är avstängd och IMAP-tidsgränsen är {seconds:d} sekunder"))
def no_watcher(env, seconds):
    start_watcher(env, settings_kw={"watch_enabled": False, "imap_timeout": seconds})


@given(parsers.parse('att Bridge hänger sig på "{command}"'))
def hang(env, command):
    env.fake.hang_on = command


@when("Bridge svarar igen")
def unhang(env):
    env.fake.hang_on = None


@when(parsers.parse("jag väntar på nya mejl i INBOX i högst {timeout:d} sekunder"))
def wait(env, timeout):
    begin = time.monotonic()
    try:
        env.result = run(env, new_mail.wait_for_new_email(env.ctx, mailbox="INBOX", timeout_seconds=timeout),
                         timeout=30)
    except Exception as exc:  # noqa: BLE001 — scenariot kontrollerar felet
        env.error = exc
    env.elapsed = time.monotonic() - begin


@then(parsers.parse("ska anropet ha gett ett fel om att Bridge inte svarade inom {seconds:d} sekunder"))
def failed_in_time(env, seconds):
    assert env.elapsed < seconds, env.elapsed
    assert isinstance(env.error, (asyncio.TimeoutError, TimeoutError)), repr(env.error)
    assert "svarade inte" in str(env.error)


@then("ska verktygens delade anslutning vara släppt")
def released(env):
    assert not env.app.imap._lock.locked()
    assert env.app.imap._client is None

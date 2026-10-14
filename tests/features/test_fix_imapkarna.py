"""BDD-tester för IMAP-anslutningens livscykel, mot en fejkad Bridge."""
import asyncio
from types import SimpleNamespace

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from tests.fix_imapkarna_fakeimap import FakeBridge

scenarios("fix_imapkarna.feature")


@pytest.fixture
def env():
    loop = asyncio.new_event_loop()
    bridge = FakeBridge()
    loop.run_until_complete(bridge.start())
    settings = Settings(username="u@example.com", password="pw", imap_port=bridge.port, _env_file=None)
    e = SimpleNamespace(loop=loop, bridge=bridge, client=IMAPClient(settings), result=None, error=None)
    # Korta timeouter så att scenarierna om uteblivna svar går snabbt
    e.client.timeout = 0.3
    e.client.uid_timeout = 0.3
    e.run = loop.run_until_complete
    yield e
    loop.run_until_complete(e.client.disconnect())
    loop.run_until_complete(bridge.stop())
    loop.close()


async def _guarded(coro, limit=5.0):
    """Kör coro men avbryt efter limit sekunder, så att ett hängande anrop blir ett testfel."""
    task = asyncio.ensure_future(coro)
    done, _ = await asyncio.wait({task}, timeout=limit)
    if not done:
        task.cancel()
        raise RuntimeError(f"Anropet hängde i mer än {limit:g} s")
    return task.result()


def _attempt(env, coro):
    try:
        env.result = env.run(_guarded(coro))
        env.error = None
    except Exception as exc:  # noqa: BLE001 — scenariot kontrollerar felet
        env.result = None
        env.error = exc


@given(parsers.parse('en Bridge med mappen "{mailbox}" som innehåller {count:d} meddelanden'))
def bridge_with_mailbox(env, mailbox, count):
    env.bridge.add_mailbox(mailbox, [f"Meddelande {i}" for i in range(1, count + 1)])


@given(parsers.parse('att jag nyss har listat mejlen i "{mailbox}"'))
def listed_mailbox(env, mailbox):
    env.run(env.client.list_messages(mailbox))


@when(parsers.parse('jag raderar meddelande {uid:d} i mappen "{mailbox}"'))
def delete_in_mailbox(env, uid, mailbox):
    _attempt(env, env.client.delete_message(mailbox, str(uid)))


@when(parsers.parse('jag söker i mappen "{mailbox}"'))
def search_in_mailbox(env, mailbox):
    _attempt(env, env.client.search_messages(mailbox, subject="Meddelande"))


@when(parsers.parse('jag listar mejlen i "{mailbox}"'))
def list_in_mailbox(env, mailbox):
    _attempt(env, env.client.list_messages(mailbox))


@then(parsers.parse('ska jag få ett fel som säger att mappen "{mailbox}" inte finns'))
def error_mailbox_missing(env, mailbox):
    assert env.error is not None, f"Inget fel, resultat: {env.result!r}"
    assert "finns inte" in str(env.error)
    assert mailbox in str(env.error)


@then("ska inga flaggor ha ändrats på servern")
def no_flags_changed(env):
    assert env.bridge.stores == []


@then(parsers.parse('ska en ny listning av "{mailbox}" visa {count:d} meddelanden'))
def relist_shows(env, mailbox, count):
    result = env.run(env.client.list_messages(mailbox))
    assert result["total"] == count
    assert len(result["messages"]) == count


@given("att Bridge nekar inloggning")
def bridge_refuses_login(env):
    env.bridge.login_reply = "NO"


@given("att Bridge inte svarar på inloggning")
def bridge_ignores_login(env):
    env.bridge.hang.add("LOGIN")


@given("att Bridge svarar på inloggning först efter en stund")
def bridge_slow_login(env):
    env.bridge.login_delay = 0.2


@when("Bridge har hunnit svara på inloggningen")
def bridge_answered_login(env):
    env.run(asyncio.sleep(0.3))
    env.bridge.login_delay = 0.0


@when("Bridge åter godtar inloggning")
def bridge_accepts_login(env):
    env.bridge.login_reply = "OK"


@when("Bridge åter svarar på inloggning")
def bridge_answers_login(env):
    env.bridge.hang.discard("LOGIN")


@when("anropet avbryts under inloggningen")
def cancel_during_login(env):
    async def go():
        task = asyncio.ensure_future(env.client.list_messages("INBOX"))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    env.run(go())


@then("ska jag få ett fel som säger att inloggningen misslyckades")
def error_login_failed(env):
    assert env.error is not None, f"Inget fel, resultat: {env.result!r}"
    assert "Inloggningen" in str(env.error)


@then("ska jag få ett timeoutfel")
def error_timeout(env):
    assert isinstance(env.error, (asyncio.TimeoutError, TimeoutError)), repr(env.error)
    assert str(env.error), "Timeoutfelet ska ha ett begripligt meddelande"


@then(parsers.parse("ska listningen visa {count:d} meddelanden"))
def listing_shows(env, count):
    assert env.error is None, repr(env.error)
    assert env.result["total"] == count


@given(parsers.parse('att Bridge aldrig svarar på "{command}"'))
def bridge_never_answers(env, command):
    env.bridge.hang.add(command)


@when(parsers.parse('jag flyttar meddelande {uid:d} från "{mailbox}" till "{target}"'))
def move_message(env, uid, mailbox, target):
    _attempt(env, env.client.move_message(mailbox, str(uid), target))

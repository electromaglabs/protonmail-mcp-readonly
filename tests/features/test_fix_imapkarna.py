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
    e.run = loop.run_until_complete
    yield e
    loop.run_until_complete(e.client.disconnect())
    loop.run_until_complete(bridge.stop())
    loop.close()


def _attempt(env, coro):
    try:
        env.result = env.run(coro)
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

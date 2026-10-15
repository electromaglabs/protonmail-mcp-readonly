"""BDD: avbrott i bevakningens väntan och i APPEND av utkast tappas inte (bpo-42130)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import imap_drafts
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.imap_idle import MailWatcher

scenarios("efterfix_l7_avbrott_ovriga.feature")

OK = SimpleNamespace(result="OK", lines=[])
LIMIT = 5.0


async def _hang(*_args, **_kwargs):
    await asyncio.Event().wait()


async def _outcome(task: asyncio.Task) -> str:
    done, _ = await asyncio.wait({task}, timeout=LIMIT)
    if not done:
        task.cancel()
        await asyncio.wait({task})
        return "hängde kvar"
    return "avbruten" if task.cancelled() else "kördes vidare"


def _settings():
    return Settings(username="u@example.com", password="pw", imap_port=1, _env_file=None)


@pytest.fixture
def state():
    return {}


@given(parsers.parse('en bevakning av "{mailbox}" som inte har några nya mejl'))
def watcher(state, mailbox):
    w = MailWatcher(_settings())
    s = w._state(mailbox)
    s.floor, s.watermark, s.uidvalidity = 0, 0, 1
    state["watcher"], state["mailbox"] = w, mailbox


@given(parsers.parse('att en klient väntar på nya mejl i "{mailbox}"'))
def waiting(state, mailbox):
    state["wait_mailbox"] = mailbox


@when("bevakningen vaknar utan nya mejl i samma ögonblick som klienten avbryter")
def wake_and_cancel(state):
    w, mailbox = state["watcher"], state["wait_mailbox"]

    async def scenario():
        task = asyncio.ensure_future(w.wait_for_messages(mailbox, 0, 1, 60))
        for _ in range(5):
            await asyncio.sleep(0)
        w._wake(w._state(mailbox))
        asyncio.get_running_loop().call_soon(task.cancel)
        state["outcome"] = await _outcome(task)

    asyncio.run(scenario())


@then("ska väntan sluta som avbruten inom några sekunder")
@then("ska sparandet sluta som avbrutet inom några sekunder")
def ended_cancelled(state):
    assert state["outcome"] == "avbruten"


@given("en IMAP-klient där Bridge aldrig svarar på sökningar")
def client(state):
    imap = IMAPClient(_settings())
    mock = AsyncMock()
    mock.select.return_value = OK
    mock.protocol = MagicMock()
    mock.protocol.state = "SELECTED"
    mock.search.side_effect = _hang
    imap._client = mock
    imap.uid_timeout = imap.timeout = 4 * LIMIT
    state["imap"] = imap


@when("klienten avbryter i samma ögonblick som Bridge svarar på APPEND av ett utkast")
def cancel_at_append(state):
    imap = state["imap"]

    async def scenario():
        holder = {}

        async def append(*_args, **_kwargs):
            asyncio.get_running_loop().call_soon(holder["task"].cancel)
            return OK

        imap._client.append.side_effect = append
        holder["task"] = task = asyncio.ensure_future(imap_drafts._store_draft(imap, b"x", "<m@x>"))
        state["outcome"] = await _outcome(task)

    asyncio.run(scenario())

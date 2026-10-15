"""Avbrott tappas inte heller i utkasten och bevakningen (bpo-42130 på Python 3.10/3.11).

Samma mönster som test_efterfix_l7_avbrott.py: attrappen schemalägger
avbrottet med call_soon i samma ögonblick som det den väntar på blir klart,
så att ordningen blir densamma varje gång, utan väntetider. Med
asyncio.wait_for på 3.10/3.11 sväljs avbrottet och uppgiften kör vidare.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aioimaplib.aioimaplib import STOP_WAIT_SERVER_PUSH

from protonmail_mcp import imap_drafts
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.imap_idle import MailWatcher

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
    if task.cancelled():
        return "avbruten"
    return f"inte avbruten: {task.exception()!r}" if task.exception() else "inte avbruten"


def _settings():
    return Settings(username="u@example.com", password="pw", imap_port=1, _env_file=None)


async def test_draft_append_cancel_at_answer_reaches_the_caller():
    imap = IMAPClient(_settings())
    mock = AsyncMock()
    mock.select.return_value = OK
    mock.protocol = MagicMock()
    mock.protocol.state = "SELECTED"
    mock.search.side_effect = _hang  # sökningen efter Message-ID (inget APPENDUID)
    imap._client = mock
    imap.uid_timeout = imap.timeout = 4 * LIMIT
    holder = {}

    async def append(*_args, **_kwargs):
        asyncio.get_running_loop().call_soon(holder["task"].cancel)
        return OK

    mock.append.side_effect = append
    holder["task"] = task = asyncio.ensure_future(imap_drafts._store_draft(imap, b"x", "<m@x>"))
    assert await _outcome(task) == "avbruten"


def _watcher() -> MailWatcher:
    return MailWatcher(_settings())


async def test_wait_for_messages_cancel_at_wakeup_reaches_the_caller():
    w = _watcher()
    state = w._state("INBOX")
    state.floor, state.watermark, state.uidvalidity = 0, 0, 1
    task = asyncio.ensure_future(w.wait_for_messages("INBOX", 0, 1, 60))
    for _ in range(5):  # låt uppgiften börja vänta (inga tider, bara schemaläggning)
        await asyncio.sleep(0)
    w._wake(state)  # väcker utan nya mejl: utan avbrott väntar den vidare
    asyncio.get_running_loop().call_soon(task.cancel)
    assert await _outcome(task) == "avbruten"


def _idle_client():
    client = MagicMock()
    client.protocol.idle_queue = asyncio.Queue()
    client.wait_server_push.side_effect = _hang
    return client


async def test_idle_start_cancel_at_answer_reaches_the_caller():
    w = _watcher()
    client = _idle_client()
    holder = {}

    async def idle_start(timeout):
        asyncio.get_running_loop().call_soon(holder["task"].cancel)
        return asyncio.get_running_loop().create_future()  # IDLE pågår

    client.idle_start.side_effect = idle_start
    imap = SimpleNamespace(timeout=4 * LIMIT)
    holder["task"] = task = asyncio.ensure_future(w._idle(imap, client))
    assert await _outcome(task) == "avbruten"


async def test_idle_done_cancel_at_answer_reaches_the_caller():
    w = _watcher()
    client = _idle_client()
    loop = asyncio.get_running_loop()
    idle = loop.create_future()
    holder = {}

    async def idle_start(timeout):
        return idle

    async def renew(timeout):
        return STOP_WAIT_SERVER_PUSH

    def idle_done():
        def answer():
            idle.set_result(None)
            holder["task"].cancel()
        loop.call_soon(answer)

    client.idle_start.side_effect = idle_start
    client.wait_server_push.side_effect = renew
    client.has_pending_idle.return_value = True
    client.idle_done.side_effect = idle_done
    imap = SimpleNamespace(timeout=4 * LIMIT)
    holder["task"] = task = asyncio.ensure_future(w._idle(imap, client))
    assert await _outcome(task) == "avbruten"


async def test_idle_start_timeout_still_reported():
    w = _watcher()
    client = _idle_client()
    client.idle_start.side_effect = _hang
    imap = SimpleNamespace(timeout=0.05)
    with pytest.raises(asyncio.TimeoutError, match="bekräftade inte IDLE"):
        await w._idle(imap, client)

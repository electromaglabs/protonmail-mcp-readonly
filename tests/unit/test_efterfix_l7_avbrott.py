"""Avbrott som sammanfaller med att ett IMAP-kommando blir klart får inte tappas.

asyncio.wait_for i Python 3.10/3.11 sväljer ett avbrott som kommer när det
inre anropet redan är klart men innan wait_for hunnit vakna (bpo-42130). Då
körde ett avbrutet verktygsanrop vidare och höll klientens lås tills nästa
kommando nådde uid_timeout (30 s). Testerna framkallar exakt den ordningen
utan väntetider: NOOP/UID-attrappen schemalägger avbrottet med call_soon
precis innan den svarar, så avbrottet körs före wait_for:s uppvaknande. Det
gör testerna stabila under last.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp import imap_client
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient

OK = SimpleNamespace(result="OK", lines=[])
# Så länge får ett avbrutet anrop högst dröja; uid_timeout sätts längre
LIMIT = 5.0


async def _hang(*_args, **_kwargs):
    await asyncio.Event().wait()


@pytest.fixture
def client():
    imap = IMAPClient(Settings(username="u@example.com", password="pw", _env_file=None))
    mock = AsyncMock()
    mock.select.return_value = OK
    mock.protocol = MagicMock()
    mock.protocol.state = "SELECTED"
    mock.uid.side_effect = _hang
    imap._client = mock
    imap.uid_timeout = imap.timeout = 4 * LIMIT
    return imap


def _cancel_when_answering(holder: dict):
    """Attrapp som avbryter anroparens uppgift i samma ögonblick som den svarar OK."""
    async def answer(*_args, **_kwargs):
        asyncio.get_running_loop().call_soon(holder["task"].cancel)
        return OK
    return answer


async def _outcome(task: asyncio.Task) -> str:
    done, _ = await asyncio.wait({task}, timeout=LIMIT)
    if not done:
        task.cancel()
        await asyncio.wait({task})
        return "hängde kvar"
    if task.cancelled():
        return "avbruten"
    return f"inte avbruten: {task.exception()!r}" if task.exception() else "inte avbruten"


async def test_cancel_when_noop_answers_reaches_the_caller(client):
    holder = {}
    mock = client._client  # kastas av _serialized efter avbrottet
    mock.noop.side_effect = _cancel_when_answering(holder)
    holder["task"] = task = asyncio.ensure_future(client.set_flags("INBOX", "1", r"(\Seen)", True))
    assert await _outcome(task) == "avbruten"
    # Avbrottet når fram vid första väntan (kontrollen av UID:t); inget skrivs
    assert all(c.args[0] != "store" for c in mock.uid.call_args_list)


async def test_lock_is_free_right_after_cancel_at_noop(client):
    holder = {}
    client._client.noop.side_effect = _cancel_when_answering(holder)
    holder["task"] = task = asyncio.ensure_future(client.set_flags("INBOX", "1", r"(\Seen)", True))
    await asyncio.wait({task}, timeout=LIMIT)
    acquired = asyncio.ensure_future(client._lock.acquire())
    done, _ = await asyncio.wait({acquired}, timeout=LIMIT)
    assert done, "låset hölls kvar efter avbrottet"
    client._lock.release()


async def test_cancel_when_uid_command_answers_reaches_the_caller(client):
    holder = {}
    client._client.uid.side_effect = _cancel_when_answering(holder)

    async def run():
        await client._uid("store", "1", "+FLAGS", r"(\Seen)")
        # _uid själv blir klar; avbrottet ska då komma vid nästa väntan, inte försvinna
        await asyncio.Event().wait()

    holder["task"] = task = asyncio.ensure_future(run())
    assert await _outcome(task) == "avbruten"


class TestTimeoutHelper:
    async def test_result_is_returned(self):
        async def quick():
            return 42
        assert await imap_client._with_timeout(quick(), 1.0) == 42

    async def test_timeout_raises_timeout_error(self):
        with pytest.raises(asyncio.TimeoutError):
            await imap_client._with_timeout(_hang(), 0.05)

    async def test_cancel_at_completion_is_not_swallowed(self):
        holder = {}

        async def answer():
            asyncio.get_running_loop().call_soon(holder["task"].cancel)
            return OK

        async def run():
            await imap_client._with_timeout(answer(), 10.0)
            await asyncio.Event().wait()

        holder["task"] = task = asyncio.ensure_future(run())
        assert await _outcome(task) == "avbruten"

    async def test_outer_cancel_is_cancelled_error_not_timeout(self):
        task = asyncio.ensure_future(imap_client._with_timeout(_hang(), 10.0))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

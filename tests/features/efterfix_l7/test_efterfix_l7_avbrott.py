"""BDD: avbrott som sammanfaller med Bridges svar tappas inte (bpo-42130 på Python 3.10/3.11)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_bdd import given, scenarios, then, when

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient

scenarios("efterfix_l7_avbrott.feature")

OK = SimpleNamespace(result="OK", lines=[])
LIMIT = 5.0


async def _hang(*_args, **_kwargs):
    await asyncio.Event().wait()


@pytest.fixture
def state():
    return {}


@given("en IMAP-klient där Bridge aldrig svarar på UID-kommandon")
def client(state):
    imap = IMAPClient(Settings(username="u@example.com", password="pw", _env_file=None))
    mock = AsyncMock()
    mock.select.return_value = OK
    mock.protocol = MagicMock()
    mock.protocol.state = "SELECTED"
    mock.uid.side_effect = _hang
    imap._client = mock
    state["mock"] = mock  # anslutningen kastas efter avbrottet
    imap.uid_timeout = imap.timeout = 4 * LIMIT
    state["imap"] = imap


@given("att klienten avbryter anropet i samma ögonblick som Bridge svarar på NOOP")
def cancel_at_noop(state):
    async def answer(*_args, **_kwargs):
        asyncio.get_running_loop().call_soon(state["task"].cancel)
        return OK
    state["imap"]._client.noop.side_effect = answer


@when('jag markerar mejlet med UID "1" i "INBOX" som läst')
def mark_read(state):
    imap = state["imap"]

    async def scenario():
        state["task"] = task = asyncio.ensure_future(imap.set_flags("INBOX", "1", r"(\Seen)", True))
        done, _ = await asyncio.wait({task}, timeout=LIMIT)
        state["outcome"] = "avbruten" if done and task.cancelled() else "hängde kvar eller kördes vidare"
        if not done:
            task.cancel()
            await asyncio.wait({task})
        acquired = asyncio.ensure_future(imap._lock.acquire())
        got, _ = await asyncio.wait({acquired}, timeout=LIMIT)
        state["lock_free"] = bool(got)
        if got:
            imap._lock.release()

    asyncio.run(scenario())


@then("ska anropet sluta som avbrutet inom några sekunder")
def ended_cancelled(state):
    assert state["outcome"] == "avbruten"


@then("ska nästa anrop kunna ta låset direkt")
def lock_free(state):
    assert state["lock_free"]


@then("ska markeringen aldrig ha skickats till Bridge")
def no_store(state):
    assert all(c.args[0] != "store" for c in state["mock"].uid.call_args_list)

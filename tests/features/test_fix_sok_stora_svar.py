"""BDD-tester: stora sökresultat hämtas i delar och max_results har tak (fix-sok, N2)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from mcp.server.fastmcp.exceptions import ToolError

from protonmail_mcp import imap_client as imap_module
from protonmail_mcp.server import mcp
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.tools import search  # noqa: F401 — registrerar verktyget
from tests.fix_sok_fakebox import imap_mock

scenarios("fix_sok_stora_svar.feature")


def _messages(result):
    return result["messages"] if isinstance(result, dict) else result


@pytest.fixture
def imap(mock_ctx, monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    client = IMAPClient(Settings(_env_file=None))
    client._client = imap_mock()
    client._client.select = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"450 EXISTS"]))
    mock_ctx.request_context.lifespan_context.imap = client
    return client


def _fetch_response(message_set, _parts, **_kwargs):
    lines = []
    for seq in message_set.split(","):
        lines += [
            f"{seq} FETCH (UID {int(seq) * 10} FLAGS () BODY[HEADER.FIELDS (DATE FROM SUBJECT)] {{20}}".encode(),
            bytearray(f"Subject: Brev {seq}\r\n\r\n".encode()),
            b")",
        ]
    return SimpleNamespace(result="OK", lines=lines)


@given(parsers.parse("att en sökning träffar {count:d} brev"))
def many_hits(imap, count):
    seqnums = " ".join(str(n) for n in range(1, count + 1))
    imap._client.search = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[seqnums.encode()]))
    imap._client.fetch = AsyncMock(side_effect=_fetch_response)


@given(parsers.parse("att metadata hämtas högst {size:d} brev åt gången"))
def chunk_size(monkeypatch, size):
    monkeypatch.setattr(imap_module, "_FETCH_CHUNK_SIZE", size)


@when(parsers.parse("jag söker med max_results {n:d}"), target_fixture="hits")
def search_with_max(imap, n):
    return _messages(asyncio.run(imap.search_messages("INBOX", max_results=n)))


@then(parsers.parse("ska jag få de {n:d} nyaste träffarna"))
def newest(hits, n):
    assert len(hits) == n
    assert hits[0]["uid"] == "4500"
    assert hits[-1]["uid"] == str((450 - n + 1) * 10)


@then(parsers.parse("ska inget FETCH-kommando ha gällt fler än {n:d} brev"))
def chunked(imap, n):
    sizes = [len(c.args[0].split(",")) for c in imap._client.fetch.call_args_list]
    assert sizes and max(sizes) <= n


@when("jag läser schemat för search_emails", target_fixture="prop")
def schema():
    return mcp._tool_manager.get_tool("search_emails").parameters["properties"]["max_results"]


@then("ska max_results ha standardvärdet 50 och vara begränsat till 1–200")
def bounded(prop):
    assert prop["default"] == 50
    assert prop["minimum"] == 1
    assert prop["maximum"] == 200


@when(parsers.parse("jag anropar search_emails med max_results {n:d}"), target_fixture="outcome")
def call_tool(mock_ctx, n):
    tool = mcp._tool_manager.get_tool("search_emails")
    try:
        return {"result": asyncio.run(tool.run({"max_results": n}, context=mock_ctx)), "error": None}
    except ToolError as e:
        return {"result": None, "error": e}


@then("ska anropet avvisas utan att något hämtas")
def rejected(outcome, imap):
    assert outcome["error"] is not None
    imap._client.fetch.assert_not_called()

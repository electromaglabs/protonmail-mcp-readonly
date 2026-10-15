"""Enhetstester: delad metadatahämtning och max_results (fix-sok, N2)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from protonmail_mcp import imap_client as imap_module
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.server import mcp
from protonmail_mcp.tools import search  # noqa: F401
from tests.fix_sok_fakebox import imap_mock
from tests import sdk_support as sdk


def _messages(result):
    return result["messages"] if isinstance(result, dict) else result


def _fetch_response(message_set, _parts, **_kwargs):
    lines = []
    for seq in message_set.split(","):
        lines += [
            f"{seq} FETCH (UID {seq} FLAGS () BODY[HEADER.FIELDS (SUBJECT)] {{9}}".encode(),
            bytearray(b"Subject: x\r\n\r\n"),
            b")",
        ]
    return SimpleNamespace(result="OK", lines=lines)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    imap = IMAPClient(Settings(_env_file=None))
    imap._client = imap_mock()
    imap._client.search = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"1 2 3 4 5"]))
    imap._client.fetch = AsyncMock(side_effect=_fetch_response)
    return imap


async def test_fetches_in_chunks(client, monkeypatch):
    monkeypatch.setattr(imap_module, "_FETCH_CHUNK_SIZE", 2)
    result = _messages(await client.search_messages("INBOX", max_results=5))
    assert [m["uid"] for m in result] == ["5", "4", "3", "2", "1"]
    assert [c.args[0] for c in client._client.fetch.call_args_list] == ["1,2", "3,4", "5"]


async def test_default_max_results_is_50(client):
    seqnums = " ".join(str(n) for n in range(1, 101)).encode()
    client._client.search = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[seqnums]))
    result = _messages(await client.search_messages("INBOX"))
    assert len(result) == 50
    assert result[0]["uid"] == "100"


async def test_max_results_below_one_rejected(client):
    with pytest.raises(ValueError, match="max_results"):
        await client.search_messages("INBOX", max_results=0)
    client._client.search.assert_not_called()


def test_tool_schema_bounds_max_results():
    prop = sdk.get_tool(mcp, "search_emails").parameters["properties"]["max_results"]
    assert (prop["default"], prop["minimum"], prop["maximum"]) == (50, 1, 200)

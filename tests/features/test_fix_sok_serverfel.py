"""BDD-tester: serverfel i sökningen döljs inte som tomma resultat (fix-sok, N5)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from tests.sdk_support import ToolError

from protonmail_mcp.server import mcp
from tests import sdk_support as sdk
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.tools import search  # noqa: F401 — registrerar verktyget
from tests.fix_sok_fakebox import imap_mock

scenarios("fix_sok_serverfel.feature")


@pytest.fixture
def imap(mock_ctx, monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    client = IMAPClient(Settings(_env_file=None))
    client._client = imap_mock()
    client._client.select = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"2 EXISTS"]))
    mock_ctx.request_context.lifespan_context.imap = client
    return client


@given(parsers.parse('att servern svarar "{result}" med texten "{text}" på SEARCH'))
def search_fails(imap, result, text):
    imap._client.search = AsyncMock(return_value=SimpleNamespace(result=result, lines=[text.encode()]))


@given("att SEARCH träffar brev 1 och 2")
def search_hits(imap):
    imap._client.search = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"1 2"]))


@given("att SEARCH inte träffar något")
def search_empty(imap):
    imap._client.search = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b""]))


@given(parsers.parse('att servern svarar "{result}" med texten "{text}" på FETCH'))
def fetch_fails(imap, result, text):
    imap._client.fetch = AsyncMock(return_value=SimpleNamespace(result=result, lines=[text.encode()]))


@when("jag söker efter olästa brev i INBOX", target_fixture="outcome")
def do_search(mock_ctx):
    tool = sdk.get_tool(mcp, "search_emails")
    try:
        return {"result": asyncio.run(tool.run({"unseen": True}, context=mock_ctx)), "error": None}
    except ToolError as e:
        return {"result": None, "error": e}


@then(parsers.parse('ska sökningen misslyckas med ett fel som innehåller "{text}"'))
def fails_with(outcome, text):
    assert outcome["error"] is not None, f"förväntade fel, fick {outcome['result']!r}"
    assert text in str(outcome["error"])


@then("ska resultatet vara tomt")
def empty(outcome):
    assert outcome["error"] is None
    result = outcome["result"]
    messages = result["messages"] if isinstance(result, dict) else result
    assert messages == []

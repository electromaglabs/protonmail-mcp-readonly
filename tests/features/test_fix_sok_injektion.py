"""BDD-tester: sökvärden kan inte injicera IMAP-kommandon (fix-sok, N1)."""
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

scenarios("fix_sok_injektion.feature")


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    return Settings(_env_file=None)


@given("att jag är ansluten till en brevlåda", target_fixture="imap")
def connected(mock_ctx, settings):
    imap = IMAPClient(settings)
    imap._client = imap_mock()
    imap._client.select = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"0 EXISTS"]))
    imap._client.search = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b""]))
    mock_ctx.request_context.lifespan_context.imap = imap
    return imap


@when(parsers.parse('jag söker med {param} "{value}"'), target_fixture="outcome")
def do_search(mock_ctx, param, value):
    # Feature-filen skriver kontrolltecken som \r och \n
    value = value.replace("\\r", "\r").replace("\\n", "\n")
    tool = sdk.get_tool(mcp, "search_emails")
    try:
        return {"result": asyncio.run(tool.run({param: value}, context=mock_ctx)), "error": None}
    except ToolError as e:
        return {"result": None, "error": e}


@then(parsers.parse('ska sökningen avvisas med ett fel som nämner "{text}"'))
def rejected(outcome, text):
    assert outcome["error"] is not None, f"förväntade fel, fick {outcome['result']!r}"
    assert text in str(outcome["error"])


@then("ska inget kommando ha skickats till servern")
def nothing_sent(imap):
    imap._client.search.assert_not_called()
    imap._client.select.assert_not_called()
    imap._client.fetch.assert_not_called()


@then(parsers.parse('ska servern ha fått sökkriteriet "{criterion}"'))
def server_got(imap, criterion):
    sent = " ".join(str(a) for a in imap._client.search.call_args.args)
    assert criterion in sent

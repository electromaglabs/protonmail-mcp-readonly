"""BDD-tester för sidindelningen i list_emails (fix-verktyg, punkt 5)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from tests.sdk_support import ToolError

from protonmail_mcp.server import mcp
from tests import sdk_support as sdk
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.tools import messages  # noqa: F401 — registrerar verktygen

scenarios("fix_verktyg_pagination.feature")


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    return Settings(_env_file=None)


@given(parsers.parse("att mappen INBOX innehåller {exists:d} meddelanden"), target_fixture="imap")
def mailbox_with_messages(mock_ctx, settings, exists):
    imap = IMAPClient(settings)
    imap._client = AsyncMock()
    imap._client.select = AsyncMock(
        return_value=SimpleNamespace(result="OK", lines=[f"{exists} EXISTS"])
    )
    # En server som inte kan räkna baklänges svarar på 1:1 med det äldsta brevet
    imap._client.fetch = AsyncMock(
        return_value=SimpleNamespace(
            result="OK",
            lines=[
                "1 FETCH (UID 1 FLAGS () BODY[HEADER.FIELDS (SUBJECT)] {15}",
                bytearray(b"Subject: Gammalt\r\n"),
                ")",
            ],
        )
    )
    mock_ctx.request_context.lifespan_context.imap = imap
    return imap


@when(
    parsers.parse("jag anropar list_emails med page {page:d} och page_size {page_size:d}"),
    target_fixture="outcome",
)
def call_list_emails(mock_ctx, page, page_size):
    tool = sdk.get_tool(mcp, "list_emails")
    try:
        result = asyncio.run(
            tool.run({"mailbox": "INBOX", "page": page, "page_size": page_size}, context=mock_ctx)
        )
        return {"result": result, "error": None}
    except ToolError as e:
        return {"result": None, "error": e}


@then(parsers.parse('ska anropet avvisas med ett valideringsfel om "{field}"'))
def rejected_with_validation_error(outcome, field):
    assert outcome["error"] is not None, f"förväntade fel, fick {outcome['result']}"
    msg = str(outcome["error"])
    assert "validation error" in msg
    assert f"\n{field}\n" in msg


@then("ingen IMAP-hämtning ska ha gjorts")
def no_fetch(imap):
    imap._client.fetch.assert_not_called()


@then("ska resultatet ha en tom meddelandelista")
def empty_messages(outcome):
    assert outcome["error"] is None, outcome["error"]
    assert outcome["result"]["messages"] == []


@then("has_more ska vara falskt")
def has_more_false(outcome):
    assert outcome["result"]["has_more"] is False


@then(parsers.parse("total ska vara {total:d} och pages {pages:d}"))
def total_and_pages(outcome, total, pages):
    assert outcome["result"]["total"] == total
    assert outcome["result"]["pages"] == pages

"""Enhetstester för sidindelningen i list_emails (fix-verktyg, punkt 5).

Givet en mapp med 12 brev
När klienten ber om en orimlig sida eller sidstorlek
Så avvisas anropet av verktygsschemat, och IMAP-lagret returnerar aldrig
brev från en sida som inte finns.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.server import mcp
from protonmail_mcp.tools import messages  # noqa: F401 — registrerar verktygen
from tests import sdk_support as sdk
from tests.sdk_support import ToolError


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    ctx.request_context.lifespan_context.imap.list_messages.return_value = {
        "messages": [], "total": 0, "page": 1, "pages": 0, "has_more": False,
    }
    return ctx


async def _run(name, args, ctx):
    return await sdk.get_tool(mcp, name).run(args, context=ctx)


class TestListEmailsSchema:
    async def test_schema_exposes_page_bounds(self):
        tools = {t.name: t for t in await mcp.list_tools()}
        props = sdk.wire(tools["list_emails"])["inputSchema"]["properties"]
        assert props["page"]["minimum"] == 1
        assert props["page_size"]["minimum"] == 1
        assert props["page_size"]["maximum"] == 100

    @pytest.mark.parametrize(
        "args",
        [
            {"page_size": 0},
            {"page_size": -2},
            {"page_size": 101},
            {"page_size": 100000},
            {"page": 0},
            {"page": -3},
        ],
    )
    async def test_invalid_page_args_are_rejected(self, mock_ctx, args):
        with pytest.raises(ToolError, match="validation error"):
            await _run("list_emails", args, mock_ctx)
        mock_ctx.request_context.lifespan_context.imap.list_messages.assert_not_called()

    @pytest.mark.parametrize("args", [{"page": 1, "page_size": 1}, {"page": 7, "page_size": 100}])
    async def test_boundary_values_are_accepted(self, mock_ctx, args):
        await _run("list_emails", args, mock_ctx)
        mock_ctx.request_context.lifespan_context.imap.list_messages.assert_called_once()


class TestListMessagesPastEnd:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        imap = IMAPClient(Settings(_env_file=None))
        imap._client = AsyncMock()
        imap._client.select = AsyncMock(
            return_value=SimpleNamespace(result="OK", lines=["12 EXISTS"])
        )
        imap._client.fetch = AsyncMock(
            return_value=SimpleNamespace(
                result="OK",
                lines=["1 FETCH (UID 1 FLAGS () BODY[HEADER.FIELDS (SUBJECT)] {15}",
                       bytearray(b"Subject: Gammalt\r\n"), ")"],
            )
        )
        return imap

    @pytest.mark.parametrize("page", [4, 99999])
    async def test_page_past_end_is_empty_and_skips_fetch(self, client, page):
        result = await client.list_messages("INBOX", page=page, page_size=5)
        assert result["messages"] == []
        assert result["total"] == 12
        assert result["pages"] == 3
        assert result["page"] == page
        assert result["has_more"] is False
        client._client.fetch.assert_not_called()

    async def test_last_partial_page_fetches_oldest(self, client):
        await client.list_messages("INBOX", page=3, page_size=5)
        client._client.fetch.assert_called_once()
        assert client._client.fetch.call_args.args[0] == "1:2"

    @pytest.mark.parametrize("kwargs", [{"page": 0}, {"page": -3}, {"page_size": 0}, {"page_size": -2}])
    async def test_invalid_values_raise_instead_of_misbehaving(self, client, kwargs):
        with pytest.raises(ValueError):
            await client.list_messages("INBOX", **kwargs)

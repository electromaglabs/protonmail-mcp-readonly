"""Enhetstester: valfria strängparametrar i search_emails json-tolkas inte (punkt 16).

FastMCP:s pre_parse_json kör json.loads på strängvärden för alla parametrar
vars annotation inte är exakt `str`. För `str | None` blir "null" då None.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.server import mcp
from protonmail_mcp.tools import search  # noqa: F401 — registrerar verktygen

STRING_PARAMS = ["from_addr", "subject", "since", "before"]


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    ctx.request_context.lifespan_context.imap.search_messages.return_value = []
    return ctx


async def _search(ctx, **args):
    await mcp._tool_manager.get_tool("search_emails").run(args, context=ctx)
    return ctx.request_context.lifespan_context.imap.search_messages.call_args.kwargs


class TestNullStringIsKept:
    @pytest.mark.parametrize("field", STRING_PARAMS)
    @pytest.mark.parametrize("value", ["null", "[1]", '{"a": 1}', "true"])
    async def test_json_looking_strings_reach_imap_unchanged(self, mock_ctx, field, value):
        kwargs = await _search(mock_ctx, **{field: value})
        assert kwargs[field] == value

    @pytest.mark.parametrize("field", STRING_PARAMS)
    async def test_explicit_null_still_means_no_filter(self, mock_ctx, field):
        kwargs = await _search(mock_ctx, **{field: None})
        assert kwargs[field] is None

    async def test_omitted_means_no_filter(self, mock_ctx):
        kwargs = await _search(mock_ctx)
        assert all(kwargs[f] is None for f in STRING_PARAMS)

    async def test_schema_still_advertises_nullable_string(self):
        tools = {t.name: t for t in await mcp.list_tools()}
        props = tools["search_emails"].inputSchema["properties"]
        for field in STRING_PARAMS:
            assert props[field]["anyOf"] == [{"type": "string"}, {"type": "null"}]
            assert props[field]["default"] is None

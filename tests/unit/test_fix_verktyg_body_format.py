"""Enhetstester för get_email-schemat: body_format och max_length (fix-verktyg, punkt 14)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from protonmail_mcp.server import mcp
from protonmail_mcp.tools import messages  # noqa: F401 — registrerar verktygen


@pytest.fixture
def mock_ctx(sample_raw_email):
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = AsyncMock()
    ctx.request_context.lifespan_context.imap.get_message.return_value = sample_raw_email
    return ctx


async def _run(args, ctx):
    return await mcp._tool_manager.get_tool("get_email").run(args, context=ctx)


class TestGetEmailSchema:
    async def test_body_format_is_enum_in_schema(self):
        tools = {t.name: t for t in await mcp.list_tools()}
        prop = tools["get_email"].inputSchema["properties"]["body_format"]
        assert sorted(prop["enum"]) == ["full", "stripped", "text"]
        assert prop["default"] == "text"

    async def test_max_length_has_minimum_zero_and_is_nullable(self):
        tools = {t.name: t for t in await mcp.list_tools()}
        prop = tools["get_email"].inputSchema["properties"]["max_length"]
        variants = prop["anyOf"]
        assert {"type": "null"} in variants
        int_variant = next(v for v in variants if v.get("type") == "integer")
        assert int_variant["minimum"] == 0
        assert prop["default"] == 500

    @pytest.mark.parametrize("fmt", ["html", "TEXT", "", "raw"])
    async def test_unknown_body_format_is_rejected(self, mock_ctx, fmt):
        with pytest.raises(ToolError, match="body_format"):
            await _run({"uid": "1", "body_format": fmt}, mock_ctx)
        mock_ctx.request_context.lifespan_context.imap.get_message.assert_not_called()

    async def test_negative_max_length_is_rejected(self, mock_ctx):
        with pytest.raises(ToolError, match="max_length"):
            await _run({"uid": "1", "max_length": -5}, mock_ctx)

    @pytest.mark.parametrize("fmt", ["text", "full", "stripped"])
    async def test_valid_formats_are_accepted(self, mock_ctx, fmt):
        result = await _run({"uid": "1", "body_format": fmt}, mock_ctx)
        assert result["subject"] == "Test subject"

    @pytest.mark.parametrize("n", [0, None, 10])
    async def test_valid_max_length_is_accepted(self, mock_ctx, n):
        result = await _run({"uid": "1", "max_length": n}, mock_ctx)
        assert result["subject"] == "Test subject"

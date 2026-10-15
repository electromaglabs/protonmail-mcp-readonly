"""Hjälp för llm-kontrakt-testerna: ett riktigt MCP-klientpass (in-memory).

Anropen går klient → FastMCP → verktyg som för en riktig modell, så att
schema, annoteringar, instruktioner och felmeddelanden testas som modellen ser
dem. Lifespan byts mot attrapper; ingenting når Bridge.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from mcp.shared.memory import create_connected_server_and_client_session

from protonmail_mcp.server import AppContext, mcp, register_tools


@asynccontextmanager
async def client_session(monkeypatch, imap=None, smtp=None):
    """ClientSession mot servern med imap/smtp-attrapper (AsyncMock som standard)."""
    register_tools()
    app = AppContext(imap=imap or AsyncMock(), smtp=smtp or AsyncMock())

    @asynccontextmanager
    async def lifespan(_server):
        yield app

    monkeypatch.setattr(mcp._mcp_server, "lifespan", lifespan)
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        yield session


def text_of(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)

"""Testernas enda väg till MCP-SDK:ns delar (in-memory-session, interna listor).

Testerna använder hjälparna här i stället för SDK:ns privata attribut
(_tool_manager, _mcp_server …) och versionsberoende typer, så att ett byte av
SDK-version (mcp 1.x → 2.x) bara ändrar den här filen och protonmail_mcp._sdk.

Resultat från klienten läses helst via wire() (wire-format, camelCase som på
ledningen), så att testerna inte beror på SDK:ns attributnamn.
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import anyio
from mcp import types
from mcp.client.session import ClientSession
from mcp.server.lowlevel.server import NotificationOptions
from mcp.shared.exceptions import McpError as MCPError
from mcp.shared.memory import create_client_server_memory_streams

from protonmail_mcp._sdk import Context, MCPServer, ToolError

__all__ = [
    "Context", "MCPError", "MCPServer", "ToolError",
    "call_tool", "capabilities", "connect", "error_message", "get_tool", "init_info",
    "init_options", "list_prompts", "list_resources", "list_templates", "list_tools",
    "lowlevel", "make_context", "patch_run", "resource_updated_uri", "set_lifespan", "wire",
]


def wire(model: Any) -> dict:
    """En SDK-modell som dict i wire-format (camelCase, utan None-fält)."""
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def lowlevel(server: MCPServer) -> Any:
    """Lågnivåservern under MCPServer (privat i SDK:n)."""
    return server._mcp_server


def set_lifespan(monkeypatch, server: MCPServer, lifespan) -> None:
    """Byt serverns lifespan (attrapper i stället för Bridge) under testet."""
    monkeypatch.setattr(lowlevel(server), "lifespan", lifespan)


@asynccontextmanager
async def connect(server: MCPServer, message_handler=None):
    """En initierad klientsession mot servern, i minnet (JSON-RPC som på riktigt).

    Sessionen har metoderna list_tools, call_tool, list_resources,
    list_resource_templates, read_resource, subscribe_resource,
    unsubscribe_resource, list_prompts och get_prompt. Skicka URI:er som str.
    """
    low = lowlevel(server)
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                lambda: low.run(server_streams[0], server_streams[1], low.create_initialization_options())
            )
            try:
                async with ClientSession(
                    client_streams[0], client_streams[1], message_handler=message_handler
                ) as session:
                    session.protonmail_init = await session.initialize()
                    yield session
            finally:
                tg.cancel_scope.cancel()


def init_info(session: Any) -> dict:
    """Det klienten fick vid anslutningen: serverInfo, instructions och capabilities."""
    result = session.protonmail_init
    return {
        "serverInfo": {"name": result.serverInfo.name, "version": result.serverInfo.version},
        "instructions": result.instructions,
        "capabilities": wire(result.capabilities),
    }


def error_message(exc: MCPError) -> str:
    """Felmeddelandet i ett JSON-RPC-fel som klienten fick."""
    return exc.error.message


def resource_updated_uri(message: Any) -> str | None:
    """URI:n i en notifications/resources/updated, annars None."""
    if isinstance(message, types.ServerNotification) and isinstance(
        message.root, types.ResourceUpdatedNotification
    ):
        return str(message.root.params.uri)
    return None


# --- Serverns registrerade delar, utan klient --------------------------------


def list_tools(server: MCPServer) -> list[Any]:
    """Registrerade verktyg (SDK:ns Tool: name, parameters, fn, fn_metadata, run)."""
    return server._tool_manager.list_tools()


def get_tool(server: MCPServer, name: str) -> Any:
    return server._tool_manager.get_tool(name)


def list_resources(server: MCPServer) -> list[Any]:
    return server._resource_manager.list_resources()


def list_templates(server: MCPServer) -> list[Any]:
    return server._resource_manager.list_templates()


def list_prompts(server: MCPServer) -> list[Any]:
    return server._prompt_manager.list_prompts()


def capabilities(server: MCPServer) -> dict:
    """Förmågorna servern annonserar vid initialize, i wire-format."""
    return wire(lowlevel(server).get_capabilities(NotificationOptions(), {}))


def init_options(server: MCPServer) -> dict:
    """Namn, version och instruktioner som servern skickar vid initialize."""
    options = lowlevel(server).create_initialization_options()
    return {"name": options.server_name, "version": options.server_version, "instructions": options.instructions}


def make_context(server: MCPServer, app: Any) -> Context:
    """En Context med app som lifespan-kontext (som under ett riktigt anrop)."""
    return Context(request_context=SimpleNamespace(lifespan_context=app), fastmcp=server)


async def call_tool(server: MCPServer, name: str, arguments: dict[str, Any], app: Any) -> Any:
    """Anropa ett verktyg genom serverns call_tool (policyspärr, schema, felomslag).

    Fel kastas som ToolError (eller ValueError från policyspärren) med
    ursprungsundantaget som __cause__.
    """
    with patch.object(server, "get_context", return_value=make_context(server, app)):
        return await server.call_tool(name, arguments)


def patch_run(monkeypatch) -> dict:
    """Byt MCPServer.run mot en som bara fångar servern: {"server": …} efter start."""
    captured: dict = {}
    monkeypatch.setattr(MCPServer, "run", lambda self, *a, **k: captured.setdefault("server", self))
    return captured

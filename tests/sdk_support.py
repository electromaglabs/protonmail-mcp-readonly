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

import anyio
from mcp import Client, types
from mcp.client._memory import InMemoryTransport
from mcp.server.lowlevel.server import NotificationOptions
from mcp.shared.exceptions import MCPError

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
    return server._lowlevel_server


def set_lifespan(monkeypatch, server: MCPServer, lifespan) -> None:
    """Byt serverns lifespan (attrapper i stället för Bridge) under testet."""
    monkeypatch.setattr(lowlevel(server), "lifespan", lifespan)


class _GatedRead:
    """Klientens läsström, som slutar läsa när stop_reading sätts.

    Som en klient som slutat läsa stdout: serverns skrivningar fastnar när
    minnesströmmens buffert är full.
    """

    def __init__(self, stream: Any, stop_reading: anyio.Event) -> None:
        self._stream = stream
        self._stop = stop_reading

    @property
    def last_context(self) -> Any:
        return getattr(self._stream, "last_context", None)

    async def __aenter__(self) -> "_GatedRead":
        await self._stream.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> Any:
        return await self._stream.__aexit__(*exc)

    def __aiter__(self) -> "_GatedRead":
        return self

    async def __anext__(self) -> Any:
        if self._stop.is_set():
            await anyio.sleep_forever()
        return await self._stream.__anext__()


@asynccontextmanager
async def _gated_transport(server: MCPServer, stop_reading: anyio.Event):
    async with InMemoryTransport(server) as (read, write):
        yield _GatedRead(read, stop_reading), write


@asynccontextmanager
async def connect(server: MCPServer, message_handler=None, *, stop_reading: anyio.Event | None = None):
    """En initierad klient mot servern, i minnet (JSON-RPC som på riktigt).

    Protokollet före 2026-07-28 (mode="legacy"), som dagens klienter talar och
    som prenumerationerna (resources/subscribe) kräver. Klienten har metoderna
    list_tools, call_tool, list_resources, list_resource_templates,
    read_resource, subscribe_resource, unsubscribe_resource, list_prompts,
    get_prompt och send_ping. Skicka URI:er som str. Inga svar cachas.

    stop_reading: när den sätts slutar klienten läsa från servern (en klient
    som hänger). Klientens notishanterare körs annars parallellt med läsningen
    och kan inte få servern att vänta.
    """
    target = server if stop_reading is None else _gated_transport(server, stop_reading)
    async with Client(target, mode="legacy", message_handler=message_handler, cache=None) as client:
        yield client


def init_info(session: Any) -> dict:
    """Det klienten fick vid anslutningen: serverInfo, instructions och capabilities."""
    return {
        "serverInfo": {"name": session.server_info.name, "version": session.server_info.version},
        "instructions": session.instructions,
        "capabilities": wire(session.server_capabilities),
    }


def error_message(exc: MCPError) -> str:
    """Felmeddelandet i ett JSON-RPC-fel som klienten fick."""
    return exc.message


def resource_updated_uri(message: Any) -> str | None:
    """URI:n i en notifications/resources/updated, annars None."""
    if isinstance(message, types.ResourceUpdatedNotification):
        return str(message.params.uri)
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


def capabilities(server: MCPServer, **notification_options: bool) -> dict:
    """Förmågorna servern annonserar vid initialize (protokoll före 2026), i wire-format.

    notification_options: t.ex. resources_changed=True (NotificationOptions).
    """
    return wire(lowlevel(server).get_capabilities(NotificationOptions(**notification_options), {}))


def init_options(server: MCPServer) -> dict:
    """Namn, version och instruktioner som servern skickar vid initialize."""
    options = lowlevel(server).create_initialization_options()
    return {"name": options.server_name, "version": options.server_version, "instructions": options.instructions}


def make_context(server: MCPServer, app: Any) -> Context:
    """En Context med app som lifespan-kontext (som under ett riktigt anrop)."""
    return Context(request_context=SimpleNamespace(lifespan_context=app), mcp_server=server)


async def call_tool(server: MCPServer, name: str, arguments: dict[str, Any], app: Any) -> Any:
    """Anropa ett verktyg genom serverns call_tool (policyspärr, schema, felomslag).

    Fel kastas som ToolError med ursprungsundantaget som __cause__.
    """
    return await server.call_tool(name, arguments, make_context(server, app))


def patch_run(monkeypatch) -> dict:
    """Byt MCPServer.run mot en som bara fångar servern: {"server": …} efter start."""
    captured: dict = {}
    monkeypatch.setattr(MCPServer, "run", lambda self, *a, **k: captured.setdefault("server", self))
    return captured

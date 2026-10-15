"""Testverktyg för llm-skick: begränsningar av vad en LLM får göra med kontot.

Den riktiga IMAPClient och SMTPClient används. "Bridge kontaktas" mäts så här:
- IMAP: _ensure_connected (första steget i varje IMAP-operation) och alla
  kommandon på aioimaplib-klienten registreras;
- SMTP: aiosmtplib.SMTP byts mot capture_smtp-attrappen, som registrerar
  varje anslutning och vad som skickas.

Verktygen anropas genom MCP-servern (mcp.call_tool), alltså samma väg som en
riktig klient, med en Context vars lifespan_context är testets AppContext.
"""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.server.fastmcp import Context

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.smtp_client import SMTPClient

KONTO = "me@proton.me"


def make_settings(**overrides: Any) -> Settings:
    overrides.setdefault("username", KONTO)
    overrides.setdefault("password", "pw")
    return Settings(_env_file=None, **overrides)


class BridgeSpy:
    """Registrerar varje försök att nå Bridge (IMAP eller SMTP)."""

    def __init__(self) -> None:
        self.imap_calls: list[str] = []
        self.smtp_connections = 0

    @property
    def contacted(self) -> bool:
        return bool(self.imap_calls) or self.smtp_connections > 0


def spy_imap(settings: Settings, spy: BridgeSpy) -> IMAPClient:
    """IMAPClient där varje anslutningsförsök och kommando registreras och vägras."""
    imap = IMAPClient(settings)

    async def ensure_connected() -> None:
        spy.imap_calls.append("_ensure_connected")
        raise AssertionError("Bridge (IMAP) kontaktades")

    imap._ensure_connected = ensure_connected  # type: ignore[method-assign]
    client = MagicMock()

    def record(name: str):
        async def call(*args, **kwargs):
            spy.imap_calls.append(name)
            raise AssertionError(f"Bridge (IMAP) fick kommandot {name}")
        return call

    for name in ("uid", "select", "append", "create", "delete", "rename", "status", "fetch", "search", "list"):
        setattr(client, name, record(name))
    imap._client = client
    return imap


def spy_smtp_patch(spy: BridgeSpy):
    """patch() som registrerar SMTP-anslutningar (och vägrar dem)."""

    def connect(*args, **kwargs):
        spy.smtp_connections += 1
        raise AssertionError("Bridge (SMTP) kontaktades")

    return patch("protonmail_mcp.smtp_client.aiosmtplib.SMTP", side_effect=connect)


@contextmanager
def record_smtp(spy: BridgeSpy):
    """Som capture_smtp, men varje SMTP-anslutning räknas i spy."""
    from tests.fix_svar_support import CapturedSMTP

    captured = CapturedSMTP()
    instance = MagicMock()
    instance.login = AsyncMock()
    instance.send_message = AsyncMock(side_effect=captured.send_message)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=instance)
    cm.__aexit__ = AsyncMock(return_value=False)

    def connect(*args, **kwargs):
        spy.smtp_connections += 1
        return cm

    with patch("protonmail_mcp.smtp_client.aiosmtplib.SMTP", side_effect=connect):
        yield captured


def make_app(settings: Settings, spy: BridgeSpy) -> SimpleNamespace:
    return SimpleNamespace(imap=spy_imap(settings, spy), smtp=SMTPClient(settings))


async def call_tool(name: str, arguments: dict[str, Any], app: Any, settings: Settings):
    """Anropa ett verktyg genom MCP-servern, som en riktig klient gör."""
    from protonmail_mcp import config
    from protonmail_mcp.server import mcp
    from protonmail_mcp.tools import (  # noqa: F401 — registrerar verktygen
        attachments, drafts, folders, labels, mailboxes, manage, messages, new_mail, reply, search, send,
        threads,
    )

    request_context = SimpleNamespace(lifespan_context=app)
    with patch.object(config, "get_settings", return_value=settings), patch.object(
        mcp, "get_context", return_value=Context(request_context=request_context, fastmcp=mcp)
    ):
        return await mcp.call_tool(name, arguments)


def registered_tools() -> set[str]:
    from protonmail_mcp.server import mcp
    from protonmail_mcp.tools import (  # noqa: F401 — registrerar verktygen
        attachments, drafts, folders, labels, mailboxes, manage, messages, new_mail, reply, search, send,
        threads,
    )

    return {tool.name for tool in mcp._tool_manager.list_tools()}


__all__ = [
    "AsyncMock",
    "BridgeSpy",
    "KONTO",
    "call_tool",
    "make_app",
    "make_settings",
    "record_smtp",
    "registered_tools",
    "spy_imap",
    "spy_smtp_patch",
]


def working_imap(settings: Settings, existing: set[str], spy: BridgeSpy | None = None) -> IMAPClient:
    """IMAPClient mot en låtsas-Bridge där UID:na i ``existing`` finns i varje mapp.

    UID FETCH (UID) svarar med de UID:n som finns; övriga kommandon svarar OK.
    """
    imap = IMAPClient(settings)

    async def ensure_connected() -> None:
        if spy is not None:
            spy.imap_calls.append("_ensure_connected")

    async def uid(command: str, *args: str):
        if spy is not None:
            spy.imap_calls.append(command)
        if command == "fetch":
            wanted = args[0].split(",")
            lines = [f"{i} FETCH (UID {u})".encode() for i, u in enumerate(wanted, 1) if u in existing]
            return SimpleNamespace(result="OK", lines=[*lines, b"FETCH completed"])
        return SimpleNamespace(result="OK", lines=[b"OK"])

    client = AsyncMock()
    client.select.return_value = SimpleNamespace(result="OK", lines=[])
    client.uid.side_effect = uid
    client.protocol = MagicMock()
    client.protocol.state = "SELECTED"
    imap._client = client
    imap._ensure_connected = ensure_connected  # type: ignore[method-assign]
    return imap

"""Facit för MCP-kontraktet: allt en klient ser av servern, som JSON.

Används som karaktäriseringssvit vid byte av MCP-SDK. Allt hämtas över ett
riktigt klientpass i minnet (tests/mcp_resurser_support.client_session) och
sparas i wire-format, så att jämförelsen inte beror på SDK:ns Python-typer.

Facitfilen skrivs om med PROTONMAIL_UPDATE_SNAPSHOT=1. Gör det bara medvetet,
granska diffen och förklara varje ändrat fält i commit-meddelandet.
"""
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

from tests import sdk_support as sdk
from tests.mcp_resurser_support import client_session, fake_imap, read_or_error

SNAPSHOT = Path(__file__).parent / "snapshots" / "mcp_kontrakt.json"

# Prefix som SDK:n lägger på fel som inte är serverns egna (engelska, utan råd)
SDK_PREFIXES = ("Error executing tool", "Error reading resource", "Error creating resource")


def _failing_imap() -> AsyncMock:
    imap = fake_imap()
    for name in ("get_message", "list_mailboxes", "get_mailbox_status", "list_messages"):
        getattr(imap, name).side_effect = ConnectionRefusedError("Connection refused")
    return imap


async def _call(session, name: str, arguments: dict) -> dict:
    try:
        result = sdk.wire(await session.call_tool(name, arguments))
    except sdk.MCPError as exc:
        return {"mcp_error": sdk.error_message(exc)}
    return {
        "isError": bool(result.get("isError")),
        "text": " ".join(c.get("text", "") for c in result["content"]),
    }


async def _read(session, uri: str) -> dict:
    text, error = await read_or_error(session, uri)
    return {"error": error} if error is not None else {"text": text}


async def listing(monkeypatch) -> dict:
    """serverInfo, instruktioner, förmågor, verktyg, resurser, mallar och promptar."""
    async with client_session(monkeypatch) as session:
        server = sdk.init_info(session)
        tools = sdk.wire(await session.list_tools())["tools"]
        resources = sdk.wire(await session.list_resources())["resources"]
        templates = sdk.wire(await session.list_resource_templates())["resourceTemplates"]
        prompts = sdk.wire(await session.list_prompts())["prompts"]
    return {
        "server": server,
        "tools": sorted(tools, key=lambda t: t["name"]),
        "resources": sorted(resources, key=lambda r: r["uri"]),
        "resourceTemplates": sorted(templates, key=lambda t: t["uriTemplate"]),
        "prompts": sorted(prompts, key=lambda p: p["name"]),
    }


async def errors(monkeypatch) -> dict:
    """Felen modellen ser i typiska fellägen (Bridge nere, fel URI, saknad parameter)."""
    out = {}
    async with client_session(monkeypatch, imap=_failing_imap()) as session:
        out["verktyg_bridge_nere"] = await _call(session, "get_email", {"uid": "42", "mailbox": "INBOX"})
        out["verktyg_okant"] = await _call(session, "finns_inte", {})
        out["verktyg_saknad_parameter"] = await _call(session, "get_email", {"mailbox": "INBOX"})
        out["resurs_bridge_nere"] = await _read(session, "email://INBOX/42")
        out["resurs_okand"] = await _read(session, "nope://x")
        out["resurs_utan_uid"] = await _read(session, "email://INBOX")
    return out


# Serverns egna fel → en fras ur den svenska texten som måste nå klienten
OWN_ERRORS = {
    "verktyg_bridge_nere": "Kan inte nå ProtonMail Bridge",
    "resurs_bridge_nere": "Kan inte nå ProtonMail Bridge",
    "resurs_utan_uid": "saknar mapp eller UID",
}


def error_text(result: dict) -> str:
    return result.get("text") or result.get("error") or result.get("mcp_error") or ""


async def policy_refusal(monkeypatch, tool: str, arguments: dict) -> dict:
    """Anropa ett verktyg med PROTONMAIL_READ_ONLY=true."""
    from protonmail_mcp import config

    async with client_session(monkeypatch) as session:
        settings = config.Settings(read_only=True)
        monkeypatch.setattr(config, "get_settings", lambda: settings)
        return await _call(session, tool, arguments)


def load() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {}


def check(section: str, actual) -> None:
    """Jämför ett avsnitt med facit; skriv om det med PROTONMAIL_UPDATE_SNAPSHOT=1."""
    data = load()
    if os.environ.get("PROTONMAIL_UPDATE_SNAPSHOT") == "1":
        data[section] = actual
        SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    assert section in data, f"{section} saknas i {SNAPSHOT.name}; kör med PROTONMAIL_UPDATE_SNAPSHOT=1"
    assert actual == data[section], f"{section} skiljer sig från {SNAPSHOT.name}"

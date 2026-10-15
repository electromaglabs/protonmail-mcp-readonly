"""Hjälp för llm-kontrakt-testerna: ett riktigt MCP-klientpass (in-memory).

Anropen går klient → servern → verktyg som för en riktig modell, så att
schema, annoteringar, instruktioner och felmeddelanden testas som modellen ser
dem. Lifespan byts mot attrapper; ingenting når Bridge.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from protonmail_mcp.server import AppContext, mcp, register_tools
from tests import sdk_support as sdk


@asynccontextmanager
async def client_session(monkeypatch, imap=None, smtp=None):
    """ClientSession mot servern med imap/smtp-attrapper (AsyncMock som standard).

    Verktygsanropen läser konfigurationen (policy, granskningslogg, lösenords-
    rensning i fel). Testerna får egna testinställningar i stället för att
    förlita sig på att ett tidigare test råkat cacha get_settings() eller att
    en .env finns, så att varje testfil kan köras ensam.
    """
    register_tools()
    use_test_settings(monkeypatch)
    app = AppContext(imap=imap or AsyncMock(), smtp=smtp or AsyncMock())

    @asynccontextmanager
    async def lifespan(_server):
        yield app

    sdk.set_lifespan(monkeypatch, mcp, lifespan)
    async with sdk.connect(mcp) as session:
        yield session


def use_test_settings(monkeypatch):
    """Testinställningar för get_settings(), oberoende av .env och tidigare tester."""
    from protonmail_mcp import config

    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    # Ingen cachad Settings från ett tidigare test (eller en riktig .env) får läcka in
    # (get_settings kan redan vara utbytt av testet; då finns ingen cache)
    cache_clear = getattr(config.get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    settings = config.Settings()
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    return settings


def text_of(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)

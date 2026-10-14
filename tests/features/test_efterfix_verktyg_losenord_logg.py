"""BDD: lösenordet läcker inte i lifespans fellogg (efterfix-verktyg, S4)."""
import asyncio
import logging

from pydantic import ValidationError
from pytest_bdd import scenarios, given, when, then, parsers

import protonmail_mcp.config as config
from protonmail_mcp.server import lifespan, mcp

scenarios("efterfix_verktyg_losenord_logg.feature")


@given(parsers.parse(
    'att PROTONMAIL_PASSWORD är "{password}" och PROTONMAIL_USERNAME saknas'
))
def password_without_username(monkeypatch, password):
    monkeypatch.delenv("PROTONMAIL_USERNAME", raising=False)
    monkeypatch.setenv("PROTONMAIL_PASSWORD", password)
    # Ingen .env får fylla i användarnamnet
    monkeypatch.setattr(config, "get_settings", lambda: config.Settings(_env_file=None))


@when("servern startar", target_fixture="outcome")
def start_server(caplog):
    async def run():
        async with lifespan(mcp):
            pass

    caplog.set_level(logging.ERROR)
    try:
        asyncio.run(run())
    except ValidationError as exc:
        return {"error": exc, "log": caplog.text}
    return {"error": None, "log": caplog.text}


@then(parsers.parse('ska starten misslyckas med ett konfigurationsfel som nämner "{field}"'))
def failed(outcome, field):
    assert outcome["error"] is not None
    assert field in str(outcome["error"])


@then(parsers.parse('ska loggen inte innehålla "{secret}"'))
def log_clean(outcome, secret):
    assert "Kunde inte läsa konfiguration" in outcome["log"]
    assert secret not in outcome["log"]


@then(parsers.parse('ska felmeddelandet inte innehålla "{secret}"'))
def error_clean(outcome, secret):
    assert secret not in str(outcome["error"])

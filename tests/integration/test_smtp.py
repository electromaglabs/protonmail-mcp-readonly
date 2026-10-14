"""Integrationstester för SMTPClient mot en riktig ProtonMail Bridge."""

import os

import pytest

from protonmail_mcp.config import get_settings

# Testet skickar ett riktigt mejl — kör det bara när det uttryckligen begärs,
# inte vid en vanlig `pytest -m integration` (som annars bara läser).
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PROTONMAIL_ALLOW_SEND") != "1",
        reason="Skickar ett riktigt mejl — sätt PROTONMAIL_ALLOW_SEND=1 för att köra",
    ),
]


async def test_send_email_to_self(smtp_client):
    """Skicka ett testmeddelande till sig själv via Bridge."""
    settings = get_settings()
    result = await smtp_client.send_email(
        to=settings.username,  # alltid till den egna adressen, aldrig hårdkodad
        subject="Integration test - protonmail-mcp",
        body="Detta är ett automatiserat integrationstest.",
    )
    assert result is True

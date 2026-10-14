"""Fixtures för integrationstester mot en riktig ProtonMail Bridge."""

import os
from pathlib import Path

import pytest

from protonmail_mcp.config import get_settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.smtp_client import SMTPClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INTEGRATION_DIR = Path(__file__).resolve().parent


def _env_available() -> bool:
    """Bridge-konfiguration finns: .env i projektroten eller PROTONMAIL_*-variabler."""
    if (PROJECT_ROOT / ".env").is_file():
        return True
    return bool(os.environ.get("PROTONMAIL_USERNAME") and os.environ.get("PROTONMAIL_PASSWORD"))


skip_without_env = pytest.mark.skip(
    reason="Kräver Bridge-konfiguration (.env eller PROTONMAIL_USERNAME/PASSWORD)",
)


# pytestmark i en conftest.py gäller inte testerna i katalogen. Därför märks
# varje test här under tests/integration som integration, så att
# addopts "-m 'not integration'" i pyproject.toml väljer bort det även om
# testfilen saknar egen pytestmark. tryfirst: före markeringsfiltret.
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    available = _env_available()
    for item in items:
        if INTEGRATION_DIR not in Path(item.path).resolve().parents:
            continue
        item.add_marker(pytest.mark.integration)
        if not available:
            item.add_marker(skip_without_env)


@pytest.fixture
async def imap_client():
    """Ansluter en IMAPClient, yield:ar den, och kopplar ner."""
    # Rensa lru_cache så att .env läses på nytt
    get_settings.cache_clear()
    settings = get_settings()
    client = IMAPClient(settings)
    await client.connect()
    yield client
    await client.disconnect()


@pytest.fixture
def smtp_client():
    """Skapar en SMTPClient (anslutning sker per send_email-anrop)."""
    get_settings.cache_clear()
    settings = get_settings()
    return SMTPClient(settings)

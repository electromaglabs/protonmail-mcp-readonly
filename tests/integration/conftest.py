"""Fixtures för integrationstester mot en riktig ProtonMail Bridge."""

import os

import pytest

from protonmail_mcp.config import get_settings
from protonmail_mcp.imap_client import IMAPClient


def _env_available() -> bool:
    """Kontrollera om .env finns i projektets rot."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.isfile(os.path.join(project_root, ".env"))


skip_without_env = pytest.mark.skipif(
    not _env_available(),
    reason="Kräver .env med Bridge-konfiguration",
)

pytestmark = [pytest.mark.integration, skip_without_env]


@pytest.fixture
async def imap_client():
    """Ansluter en IMAPClient, yield:ar den, och kopplar ner."""
    # pytestmark in a conftest does not reach the test modules, so skip here
    if not _env_available():
        pytest.skip("Needs a .env with Bridge settings")
    # Clear lru_cache so .env is read again
    get_settings.cache_clear()
    settings = get_settings()
    client = IMAPClient(settings)
    await client.connect()
    yield client
    await client.disconnect()

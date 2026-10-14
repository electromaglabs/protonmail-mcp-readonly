"""Testhjälp för fix-sok-testerna."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def imap_mock() -> AsyncMock:
    """aioimaplib.IMAP4-attrapp: inloggad, SELECT svarar OK (som _imap_mock i test_imap_client.py)."""
    m = AsyncMock()
    m.select.return_value = SimpleNamespace(result="OK", lines=[])
    m.login.return_value = SimpleNamespace(result="OK", lines=[])
    m.protocol = MagicMock()
    m.protocol.state = "SELECTED"
    return m

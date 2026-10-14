"""search_messages hämtar TO och MESSAGE-ID, inte bara DATE FROM SUBJECT (K7)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from tests.fix_sok_fakebox import imap_mock


@pytest.mark.parametrize("subject", [None, "Hej"])
async def test_search_fetches_to_and_message_id(subject):
    imap = IMAPClient(Settings(username="u", password="p", _env_file=None))
    imap._client = imap_mock()
    imap._client.select.return_value = SimpleNamespace(result="OK", lines=[b"1 EXISTS"])
    imap._client.search = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"1"]))
    imap._client.fetch = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[]))
    await imap.search_messages("INBOX", subject=subject, unseen=True)
    parts = imap._client.fetch.call_args.args[1]
    assert "TO" in parts.split("(")[-1].split()
    assert "MESSAGE-ID" in parts

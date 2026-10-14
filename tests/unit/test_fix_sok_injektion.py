"""Enhetstester: strikt validering av allt som interpoleras i SEARCH (fix-sok, N1)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from protonmail_mcp.imap_client import IMAPClient, _imap_quoted, _to_imap_date
from tests.fix_sok_fakebox import imap_mock


class TestImapQuoted:
    def test_quotes_and_escapes(self):
        assert _imap_quoted('a"b\\c', "subject") == '"a\\"b\\\\c"'

    @pytest.mark.parametrize("bad", ["x\r\nZZ1 EXPUNGE", "x\nY", "x\rY", "x\x00", "x\x7f", "x\x1b"])
    def test_rejects_control_characters(self, bad):
        with pytest.raises(ValueError, match="subject"):
            _imap_quoted(bad, "subject")

    def test_allows_non_ascii_letters(self):
        assert _imap_quoted("Fjällklubben", "subject") == '"Fjällklubben"'


class TestToImapDateStrict:
    @pytest.mark.parametrize("value,expected", [
        ("2024-01-15", "15-Jan-2024"),
        ("2026-03-01", "01-Mar-2026"),
        ("15-Jan-2024", "15-Jan-2024"),
        ("1-Mar-2026", "01-Mar-2026"),
        ("15-jan-2024", "15-Jan-2024"),
        (" 2024-01-15 ", "15-Jan-2024"),
    ])
    def test_accepts_supported_formats(self, value, expected):
        assert _to_imap_date(value) == expected

    @pytest.mark.parametrize("bad", [
        "2024/01/05",
        "01-Jan-2020\r\nZZ3 UID STORE 1:* +FLAGS (\\Deleted)",
        "2024-13-01",
        "31-Feb-2024",
        "yesterday",
        "",
        "15-Jan-24",
    ])
    def test_rejects_everything_else(self, bad):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            _to_imap_date(bad)

    def test_independent_of_locale(self, monkeypatch):
        import locale
        try:
            locale.setlocale(locale.LC_TIME, "sv_SE.UTF-8")
        except locale.Error:
            pytest.skip("sv_SE saknas")
        try:
            assert _to_imap_date("2024-05-15") == "15-May-2024"
            assert _to_imap_date("15-May-2024") == "15-May-2024"
        finally:
            locale.setlocale(locale.LC_TIME, "C")


class TestSearchRejectsInjection:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        imap = IMAPClient(Settings(_env_file=None))
        imap._client = imap_mock()
        imap._client.search = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b""]))
        return imap

    @pytest.mark.parametrize("kwargs,field", [
        ({"subject": "x\r\nZZ1 EXPUNGE\r\nZZ2 NOOP"}, "subject"),
        ({"from_addr": 'a"\r\nX1 DELETE INBOX'}, "from_addr"),
        ({"since": "01-Jan-2020\r\nZZ3 UID STORE 1:* +FLAGS (\\Deleted)"}, "since"),
        ({"before": "01-Jan-2026\nX1 DELETE INBOX"}, "before"),
    ])
    async def test_rejected_before_any_command(self, client, kwargs, field):
        with pytest.raises(ValueError, match=field):
            await client.search_messages("INBOX", **kwargs)
        client._client.select.assert_not_called()
        client._client.search.assert_not_called()

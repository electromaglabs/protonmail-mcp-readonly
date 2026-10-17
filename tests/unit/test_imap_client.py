"""Tester för imap_client.py — validering, escaping, parsning och IMAP-operationer."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from types import SimpleNamespace

from protonmail_mcp.imap_client import (
    _validate_uid,
    _validate_mailbox,
    _escape_imap_string,
    _parse_seqnums,
    _parse_fetch_metadata,
    _parse_list_line,
    _parse_headers,
    _to_imap_date,
    IMAPClient,
)


# ---------------------------------------------------------------------------
# _validate_uid
# ---------------------------------------------------------------------------
class TestValidateUid:
    def test_valid_numeric_uid(self):
        assert _validate_uid("123") == "123"

    def test_rejects_sequence_set(self):
        with pytest.raises(ValueError, match="Invalid UID"):
            _validate_uid("1:*")

    def test_rejects_injection_attempt(self):
        with pytest.raises(ValueError, match="Invalid UID"):
            _validate_uid("123 STORE")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="Invalid UID"):
            _validate_uid("")

    def test_rejects_negative(self):
        with pytest.raises(ValueError, match="Invalid UID"):
            _validate_uid("-1")


# ---------------------------------------------------------------------------
# _validate_mailbox
# ---------------------------------------------------------------------------
class TestValidateMailbox:
    def test_validate_mailbox_valid(self):
        assert _validate_mailbox("INBOX") == "INBOX"
        assert _validate_mailbox("Folders/Sub") == "Folders/Sub"
        assert _validate_mailbox("Labels/Arbete") == "Labels/Arbete"

    def test_validate_mailbox_rejects_wildcard(self):
        with pytest.raises(ValueError, match="Invalid mailbox name"):
            _validate_mailbox("INBOX*")

    def test_validate_mailbox_rejects_dotdot(self):
        with pytest.raises(ValueError, match="Invalid mailbox name"):
            _validate_mailbox("../etc/passwd")

    def test_validate_mailbox_rejects_control_chars(self):
        with pytest.raises(ValueError, match="Invalid mailbox name"):
            _validate_mailbox("INBOX\x00")
        with pytest.raises(ValueError, match="Invalid mailbox name"):
            _validate_mailbox("IN\nBOX")


# ---------------------------------------------------------------------------
# _to_imap_date
# ---------------------------------------------------------------------------
class TestToImapDate:
    def test_to_imap_date_converts_iso(self):
        assert _to_imap_date("2024-01-15") == "15-Jan-2024"
        assert _to_imap_date("2026-03-01") == "01-Mar-2026"

    def test_to_imap_date_passthrough_existing_format(self):
        assert _to_imap_date("15-Jan-2024") == "15-Jan-2024"
        assert _to_imap_date("01-Mar-2026") == "01-Mar-2026"


# ---------------------------------------------------------------------------
# _escape_imap_string
# ---------------------------------------------------------------------------
class TestEscapeImapString:
    def test_normal_string_unchanged(self):
        assert _escape_imap_string("normal") == "normal"

    def test_escapes_double_quote(self):
        assert _escape_imap_string('with"quote') == 'with\\"quote'

    def test_escapes_backslash(self):
        assert _escape_imap_string("with\\back") == "with\\\\back"

    def test_escapes_both(self):
        assert _escape_imap_string('a\\"b') == 'a\\\\\\"b'


# ---------------------------------------------------------------------------
# _parse_seqnums
# ---------------------------------------------------------------------------
class TestParseSeqnums:
    def test_ok_response_with_numbers(self):
        resp = SimpleNamespace(result="OK", lines=[b"1 2 3 45"])
        assert _parse_seqnums(resp) == ["1", "2", "3", "45"]

    def test_filters_non_digits(self):
        resp = SimpleNamespace(result="OK", lines=[b"1 SEARCH 2 3"])
        assert _parse_seqnums(resp) == ["1", "2", "3"]

    def test_not_ok_returns_empty(self):
        resp = SimpleNamespace(result="NO", lines=[b"1 2 3"])
        assert _parse_seqnums(resp) == []

    def test_empty_lines_returns_empty(self):
        resp = SimpleNamespace(result="OK", lines=[])
        assert _parse_seqnums(resp) == []


# ---------------------------------------------------------------------------
# _parse_list_line
# ---------------------------------------------------------------------------
class TestParseListLine:
    def test_quoted_name(self):
        assert _parse_list_line('(\\HasNoChildren) "/" "INBOX"') == "INBOX"

    def test_unquoted_name(self):
        assert _parse_list_line('(\\HasNoChildren) "/" Sent') == "Sent"

    def test_subfolder(self):
        assert _parse_list_line('(\\HasNoChildren) "/" "Folders/Sub"') == "Folders/Sub"

    def test_command_line_skipped(self):
        assert _parse_list_line("command completed") is None

    def test_empty_line_skipped(self):
        assert _parse_list_line("") is None

    def test_non_matching_line(self):
        assert _parse_list_line("garbage data") is None


# ---------------------------------------------------------------------------
# _parse_headers
# ---------------------------------------------------------------------------
class TestParseHeaders:
    def test_parses_basic_headers(self):
        raw = b"Subject: Hello\r\nFrom: a@b.com\r\n"
        result = _parse_headers(raw)
        assert result["subject"] == "Hello"
        assert result["from"] == "a@b.com"

    def test_empty_bytes(self):
        assert _parse_headers(b"") == {}

    def test_header_with_colon_in_value(self):
        raw = b"Subject: Re: Hello\r\n"
        result = _parse_headers(raw)
        assert result["subject"] == "Re: Hello"


# ---------------------------------------------------------------------------
# _parse_fetch_metadata
# ---------------------------------------------------------------------------
class TestParseFetchMetadata:
    def test_parses_uid_flags_and_headers(self):
        lines = [
            '1 FETCH (UID 42 FLAGS (\\Seen \\Flagged) BODY[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)] {120}',
            bytearray(
                b"Subject: Test mail\r\n"
                b"From: alice@example.com\r\n"
                b"To: bob@example.com\r\n"
                b"Date: Mon, 16 Mar 2026 10:00:00 +0100\r\n"
                b"Message-ID: <abc@example.com>\r\n"
            ),
            ")",
        ]
        result = _parse_fetch_metadata(lines)
        assert len(result) == 1
        msg = result[0]
        assert msg["uid"] == "42"
        assert "\\Seen" in msg["flags"]
        assert "\\Flagged" in msg["flags"]
        assert msg["subject"] == "Test mail"
        assert msg["from"] == "alice@example.com"
        assert msg["to"] == "bob@example.com"
        assert msg["date"] == "Mon, 16 Mar 2026 10:00:00 +0100"
        assert msg["message_id"] == "<abc@example.com>"

    def test_multiple_messages(self):
        lines = [
            '1 FETCH (UID 10 FLAGS () BODY[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)] {50}',
            bytearray(b"Subject: First\r\nFrom: a@b.com\r\n"),
            ")",
            '2 FETCH (UID 20 FLAGS (\\Seen) BODY[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)] {50}',
            bytearray(b"Subject: Second\r\nFrom: c@d.com\r\n"),
            ")",
        ]
        result = _parse_fetch_metadata(lines)
        assert len(result) == 2
        assert result[0]["uid"] == "10"
        assert result[1]["uid"] == "20"

    def test_no_header_bytearray(self):
        """FETCH-rad utan efterföljande bytearray — headers ska vara tomma."""
        lines = [
            '1 FETCH (UID 99 FLAGS (\\Seen) BODY[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)] {0}',
            ")",
        ]
        result = _parse_fetch_metadata(lines)
        assert len(result) == 1
        assert result[0]["uid"] == "99"
        assert result[0]["subject"] == ""


# ---------------------------------------------------------------------------
# IMAPClient.list_mailboxes
# ---------------------------------------------------------------------------
class TestListMailboxes:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        imap = IMAPClient(settings)
        imap._client = AsyncMock()
        imap._client.examine = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[]))
        return imap

    @pytest.mark.asyncio
    async def test_parses_mailbox_names(self, client):
        client._client.list = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[
                '(\\HasNoChildren) "/" "INBOX"',
                '(\\HasNoChildren) "/" "Sent"',
                '(\\HasNoChildren) "/" "Folders/Sub"',
                'command completed',
            ],
        ))
        result = await client.list_mailboxes()
        names = [m["name"] for m in result]
        assert "INBOX" in names
        assert "Sent" in names
        assert "Folders/Sub" in names

    @pytest.mark.asyncio
    async def test_empty_on_failure(self, client):
        client._client.list = AsyncMock(return_value=SimpleNamespace(
            result="NO",
            lines=[],
        ))
        result = await client.list_mailboxes()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_mailboxes_returns_type_folder(self, client):
        """Vanlig mapp ska ha type='folder'."""
        client._client.list = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[
                '(\\HasNoChildren) "/" "INBOX"',
                'command completed',
            ],
        ))
        result = await client.list_mailboxes()
        assert len(result) == 1
        assert result[0] == {"name": "INBOX", "type": "folder"}

    @pytest.mark.asyncio
    async def test_list_mailboxes_returns_type_label(self, client):
        """Labels/Arbete ska ha type='label'."""
        client._client.list = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[
                '(\\HasNoChildren) "/" "Labels/Arbete"',
                'command completed',
            ],
        ))
        result = await client.list_mailboxes()
        assert len(result) == 1
        assert result[0] == {"name": "Labels/Arbete", "type": "label"}

    @pytest.mark.asyncio
    async def test_list_mailboxes_mixed(self, client):
        """Blandat mappar och labels ska ge rätt type på alla."""
        client._client.list = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[
                '(\\HasNoChildren) "/" "INBOX"',
                '(\\HasNoChildren) "/" "Sent"',
                '(\\HasNoChildren) "/" "Labels/Arbete"',
                '(\\HasNoChildren) "/" "Labels/Privat"',
                '(\\HasNoChildren) "/" "Folders/Projekt"',
                'command completed',
            ],
        ))
        result = await client.list_mailboxes()
        assert len(result) == 5
        types = {m["name"]: m["type"] for m in result}
        assert types["INBOX"] == "folder"
        assert types["Sent"] == "folder"
        assert types["Labels/Arbete"] == "label"
        assert types["Labels/Privat"] == "label"
        assert types["Folders/Projekt"] == "folder"


# ---------------------------------------------------------------------------
# IMAPClient.get_message
# ---------------------------------------------------------------------------
class TestGetMessage:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        imap = IMAPClient(settings)
        imap._client = AsyncMock()
        imap._client.examine = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[]))
        return imap

    @pytest.mark.asyncio
    async def test_returns_bytes_from_bytearray(self, client):
        raw_email = bytearray(b"From: a@b.com\r\nSubject: Hi\r\n\r\nBody here")
        client._client.uid = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[
                '1 FETCH (BODY[] {40}',
                raw_email,
                ")",
            ],
        ))
        result = await client.get_message("INBOX", "42")
        assert isinstance(result, bytes)
        assert result == bytes(raw_email)

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self, client):
        client._client.uid = AsyncMock(return_value=SimpleNamespace(
            result="NO",
            lines=[],
        ))
        result = await client.get_message("INBOX", "42")
        assert result is None

    @pytest.mark.asyncio
    async def test_validates_uid(self, client):
        with pytest.raises(ValueError, match="Invalid UID"):
            await client.get_message("INBOX", "1:*")

    @pytest.mark.asyncio
    async def test_returns_none_when_ok_but_no_bytearray(self, client):
        """OK-respons utan bytearray-data ska returnera None."""
        client._client.uid = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[
                '1 FETCH (BODY[] {0}',
                ")",
            ],
        ))
        result = await client.get_message("INBOX", "42")
        assert result is None


# ---------------------------------------------------------------------------
# IMAPClient.search_messages — escaping
# ---------------------------------------------------------------------------
class TestSearchMessages:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        imap = IMAPClient(settings)
        imap._client = AsyncMock()
        imap._client.examine = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[]))
        return imap

    @pytest.mark.asyncio
    async def test_escapes_from_addr_with_quote(self, client):
        """from_addr med " ska escapas korrekt i IMAP-sökkriterierna."""
        client._client.search = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[b"1"],
        ))
        client._client.fetch = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=['1 FETCH (UID 100)'],
        ))
        await client.search_messages("INBOX", from_addr='user"name@example.com')
        # Verifiera att search anropades med escaped sträng
        call_args = client._client.search.call_args[0][0]
        assert '\\"' in call_args
        assert 'user\\"name@example.com' in call_args


# ---------------------------------------------------------------------------
# IMAPClient.connect — error paths
# ---------------------------------------------------------------------------
class TestConnectErrors:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        return IMAPClient(settings)

    @pytest.mark.asyncio
    async def test_timeout_during_connect(self, client, monkeypatch):
        """asyncio.TimeoutError från wait_hello_from_server ska bubbla upp."""
        import asyncio

        mock_imap = AsyncMock()
        mock_imap.wait_hello_from_server = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=mock_imap):
            with pytest.raises(asyncio.TimeoutError):
                await client.connect()

    @pytest.mark.asyncio
    async def test_login_failure(self, client, monkeypatch):
        """Login som kastar exception ska bubbla upp."""
        mock_imap = AsyncMock()
        mock_imap.wait_hello_from_server = AsyncMock()
        mock_imap.login = AsyncMock(side_effect=Exception("LOGIN failed"))

        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=mock_imap):
            with pytest.raises(Exception, match="LOGIN failed"):
                await client.connect()


# ---------------------------------------------------------------------------
# IMAPClient._ensure_connected — NOOP reconnect
# ---------------------------------------------------------------------------
class TestEnsureConnectedReconnect:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        return IMAPClient(settings)

    @pytest.mark.asyncio
    async def test_ensure_connected_reconnects_on_noop_failure(self, client):
        """Om NOOP misslyckas ska klienten återansluta."""
        mock_old_client = AsyncMock()
        mock_old_client.noop = AsyncMock(side_effect=Exception("Connection lost"))
        client._client = mock_old_client

        mock_new_client = AsyncMock()
        mock_new_client.wait_hello_from_server = AsyncMock()
        mock_new_client.login = AsyncMock(return_value=SimpleNamespace(result="OK"))

        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=mock_new_client):
            await client._ensure_connected()

        # Gamla klienten ska vara borta, ny klient ska vara satt
        assert client._client is mock_new_client
        mock_new_client.login.assert_awaited_once()


# ---------------------------------------------------------------------------
# IMAPClient.list_mailboxes — BAD result
# ---------------------------------------------------------------------------
class TestListMailboxesBadResult:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        imap = IMAPClient(settings)
        imap._client = AsyncMock()
        imap._client.examine = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[]))
        return imap

    @pytest.mark.asyncio
    async def test_bad_result_returns_empty(self, client):
        """list() med result='BAD' ska returnera tom lista."""
        client._client.list = AsyncMock(return_value=SimpleNamespace(
            result="BAD",
            lines=["some error"],
        ))
        result = await client.list_mailboxes()
        assert result == []


# ---------------------------------------------------------------------------
# IMAPClient.search_messages — metadata dicts
# ---------------------------------------------------------------------------
class TestSearchMessagesMetadata:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        imap = IMAPClient(settings)
        imap._client = AsyncMock()
        imap._client.examine = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[]))
        return imap

    @pytest.mark.asyncio
    async def test_search_messages_returns_metadata_dicts(self, client):
        """search_messages ska returnera lista med dicts (uid, subject, from, date, flags)."""
        client._client.search = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[b"1 2"],
        ))
        client._client.fetch = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[
                '1 FETCH (UID 100 FLAGS (\\Seen) BODY[HEADER.FIELDS (DATE FROM SUBJECT)] {80}',
                bytearray(b"Subject: Hello\r\nFrom: alice@example.com\r\nDate: Mon, 16 Mar 2026 10:00:00 +0100\r\n"),
                ")",
                '2 FETCH (UID 200 FLAGS () BODY[HEADER.FIELDS (DATE FROM SUBJECT)] {60}',
                bytearray(b"Subject: World\r\nFrom: bob@example.com\r\n"),
                ")",
            ],
        ))
        result = await client.search_messages("INBOX")
        assert isinstance(result, list)
        assert len(result) == 2
        # Nyaste först (reverserad)
        assert result[0]["uid"] == "200"
        assert result[1]["uid"] == "100"
        assert result[1]["subject"] == "Hello"
        assert result[1]["from"] == "alice@example.com"
        assert "\\Seen" in result[1]["flags"]

    @pytest.mark.asyncio
    async def test_search_messages_empty_returns_empty_list(self, client):
        """Tom sökning ska returnera tom lista."""
        client._client.search = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[b""],
        ))
        result = await client.search_messages("INBOX")
        assert result == []


# ---------------------------------------------------------------------------
# IMAPClient.search_messages — empty search response
# ---------------------------------------------------------------------------
class TestSearchMessagesEmpty:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        imap = IMAPClient(settings)
        imap._client = AsyncMock()
        imap._client.examine = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[]))
        return imap

    @pytest.mark.asyncio
    async def test_empty_search_returns_empty(self, client):
        """search som returnerar OK men tom rad ska ge tom lista."""
        client._client.search = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[b""],
        ))
        result = await client.search_messages("INBOX")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_no_result_returns_empty(self, client):
        """search som returnerar NO ska ge tom lista."""
        client._client.search = AsyncMock(return_value=SimpleNamespace(
            result="NO",
            lines=[],
        ))
        result = await client.search_messages("INBOX", from_addr="nobody@example.com")
        assert result == []


# ---------------------------------------------------------------------------
# IMAPClient.get_message_headers
# ---------------------------------------------------------------------------
class TestGetMessageHeaders:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        imap = IMAPClient(settings)
        imap._client = AsyncMock()
        imap._client.examine = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[]))
        return imap

    @pytest.mark.asyncio
    async def test_get_message_headers_returns_dict(self, client):
        client._client.uid = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[
                '1 FETCH (BODY[HEADER.FIELDS ...] {100}',
                bytearray(b"From: alice@example.com\r\nTo: bob@example.com\r\nSubject: Test\r\nDate: Mon, 16 Mar 2026\r\nMessage-ID: <abc@ex>\r\nReply-To: reply@ex.com\r\nCc: cc@ex.com\r\n"),
                ")",
            ],
        ))
        result = await client.get_message_headers("INBOX", "42")
        assert isinstance(result, dict)
        assert result["from"] == "alice@example.com"
        assert result["to"] == "bob@example.com"
        assert result["subject"] == "Test"
        assert result["message-id"] == "<abc@ex>"

    @pytest.mark.asyncio
    async def test_get_message_headers_returns_none_on_bad_result(self, client):
        client._client.uid = AsyncMock(return_value=SimpleNamespace(
            result="NO",
            lines=[],
        ))
        result = await client.get_message_headers("INBOX", "42")
        assert result is None


# ---------------------------------------------------------------------------
# IMAPClient.list_messages — page-baserad pagination
# ---------------------------------------------------------------------------
class TestListMessagesPagination:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        imap = IMAPClient(settings)
        imap._client = AsyncMock()
        imap._client.examine = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[]))
        return imap

    def _make_select_resp(self, exists: int):
        return SimpleNamespace(result="OK", lines=[f"{exists} EXISTS"])

    def _make_fetch_resp(self, uids: list[int]):
        """Bygger ett FETCH-svar med givna UID:n (i sekvensordning)."""
        lines = []
        for uid in uids:
            lines.append(
                f'1 FETCH (UID {uid} FLAGS () BODY[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)] {{50}}'
            )
            lines.append(bytearray(f"Subject: Mail {uid}\r\nFrom: a@b.com\r\n".encode()))
            lines.append(")")
        return SimpleNamespace(result="OK", lines=lines)

    @pytest.mark.asyncio
    async def test_list_messages_returns_pagination_envelope(self, client):
        """Returvärdet ska ha nycklar: messages, total, page, pages, has_more."""
        client._client.examine = AsyncMock(return_value=self._make_select_resp(5))
        client._client.fetch = AsyncMock(return_value=self._make_fetch_resp([1, 2, 3, 4, 5]))

        result = await client.list_messages("INBOX", page=1, page_size=20)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"messages", "total", "page", "pages", "has_more"}
        assert isinstance(result["messages"], list)

    @pytest.mark.asyncio
    async def test_list_messages_page1(self, client):
        """page=1, page_size=5, total=12 → has_more=True, pages=3."""
        client._client.examine = AsyncMock(return_value=self._make_select_resp(12))
        client._client.fetch = AsyncMock(return_value=self._make_fetch_resp([8, 9, 10, 11, 12]))

        result = await client.list_messages("INBOX", page=1, page_size=5)
        assert result["total"] == 12
        assert result["page"] == 1
        assert result["pages"] == 3
        assert result["has_more"] is True
        assert len(result["messages"]) == 5

    @pytest.mark.asyncio
    async def test_list_messages_last_page(self, client):
        """Sista sidan → has_more=False, rätt antal meddelanden."""
        client._client.examine = AsyncMock(return_value=self._make_select_resp(12))
        client._client.fetch = AsyncMock(return_value=self._make_fetch_resp([1, 2]))

        result = await client.list_messages("INBOX", page=3, page_size=5)
        assert result["total"] == 12
        assert result["page"] == 3
        assert result["pages"] == 3
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_messages_empty_mailbox(self, client):
        """Tom mailbox → total=0, pages=0, tom messages-lista."""
        client._client.examine = AsyncMock(return_value=self._make_select_resp(0))

        result = await client.list_messages("INBOX", page=1, page_size=20)
        assert isinstance(result, dict)
        assert result["total"] == 0
        assert result["pages"] == 0
        assert result["has_more"] is False
        assert result["messages"] == []


# ===========================================================================
# Read-only fork: tests for the security fixes
# ===========================================================================
from protonmail_mcp.imap_client import (  # noqa: E402
    _ALLOWED_COMMANDS,
    _check_outgoing_line,
    _install_readonly_guard,
    _search_string,
)

OK = SimpleNamespace(result="OK", lines=[])


def _make_client(monkeypatch, allowed=None):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    if allowed is None:
        monkeypatch.delenv("PROTONMAIL_ALLOWED_MAILBOXES", raising=False)
    else:
        monkeypatch.setenv("PROTONMAIL_ALLOWED_MAILBOXES", allowed)
    from protonmail_mcp.config import Settings
    imap = IMAPClient(Settings(_env_file=None))
    imap._client = AsyncMock()
    imap._client.examine = AsyncMock(return_value=OK)
    imap._client.search = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b""]))
    return imap


class TestValidationRejectsTrailingNewline:
    """re "$" also matches before a final newline; validation must not."""

    @pytest.mark.parametrize("uid", ["5\n", "5\r\n", "5 ", " 5", "5\n6", "", "12345678901"])
    def test_uid(self, uid):
        with pytest.raises(ValueError):
            _validate_uid(uid)

    @pytest.mark.parametrize("name", ["INBOX\n", "INBOX\r\n", "INBOX\r", "a\nb", 'a"b', "a\\b", ""])
    def test_mailbox(self, name):
        with pytest.raises(ValueError):
            _validate_mailbox(name)

    def test_mailbox_with_spaces_is_valid(self):
        assert _validate_mailbox("Folders/My Stuff") == "Folders/My Stuff"


class TestDatesAreStrict:
    @pytest.mark.parametrize("value,expected", [
        ("2026-01-01", "01-Jan-2026"),
        ("2024-02-29", "29-Feb-2024"),
        ("1-jan-2026", "01-Jan-2026"),
        ("31-DEC-2025", "31-Dec-2025"),
    ])
    def test_accepts_and_normalises(self, value, expected):
        assert _to_imap_date(value) == expected

    @pytest.mark.parametrize("value", [
        '01-Jan-2026\r\nZZ99 DELETE "Folders/Important"',
        "01-Jan-2026\nA1 DELETE x",
        "01-Jan-2026 OR SEEN UNSEEN",
        "2026-01-01 ",
        "2026-01-01\n",
        "2026-13-01",
        "2026-02-30",
        "32-Jan-2026",
        "01-Foo-2026",
        "yesterday",
        "",
        "ALL",
    ])
    def test_rejects_everything_else(self, value):
        with pytest.raises(ValueError):
            _to_imap_date(value)


class TestSearchStringsAreStrict:
    def test_quotes_and_escapes(self):
        assert _search_string('a"b\\c', "subject") == '"a\\"b\\\\c"'

    @pytest.mark.parametrize("value", [
        'x"\r\nZZ98 DELETE foo', "line1\nline2", "tab\there", "nul\x00", "del\x7f", "x" * 201,
    ])
    def test_rejects_control_characters_and_long_values(self, value):
        with pytest.raises(ValueError):
            _search_string(value, "subject")


class TestSearchInjectionIsBlocked:
    """The original bug: a line break in a search filter became a second IMAP command."""

    @pytest.mark.parametrize("kwargs", [
        {"since": '01-Jan-2026\r\nZZ99 DELETE "Folders/Important"'},
        {"before": "01-Jan-2026\r\nZZ99 DELETE x"},
        {"subject": 'x"\r\nZZ98 DELETE foo'},
        {"from_addr": "a@b.co\r\nZZ97 DELETE foo"},
        {"since": "01-Jan-2026 OR SEEN UNSEEN"},
    ])
    async def test_rejected_before_anything_is_sent(self, monkeypatch, kwargs):
        client = _make_client(monkeypatch)
        with pytest.raises(ValueError):
            await client.search_messages("INBOX", **kwargs)
        client._client.examine.assert_not_called()
        client._client.search.assert_not_called()

    async def test_valid_search_is_single_line(self, monkeypatch):
        client = _make_client(monkeypatch)
        await client.search_messages("INBOX", subject="hello", since="2026-01-01", unseen=True)
        criteria = client._client.search.call_args[0][0]
        assert criteria == 'SUBJECT "hello" SINCE 01-Jan-2026 UNSEEN'


class TestReadsDoNotChangeTheMailbox:
    async def test_mailbox_is_opened_with_examine_and_quoted(self, monkeypatch):
        client = _make_client(monkeypatch)
        client._client.uid = AsyncMock(return_value=SimpleNamespace(result="NO", lines=[]))
        await client.get_message("Folders/My Stuff", "42")
        client._client.examine.assert_awaited_once_with('"Folders/My Stuff"')
        client._client.select.assert_not_called()

    async def test_get_message_uses_peek(self, monkeypatch):
        client = _make_client(monkeypatch)
        client._client.uid = AsyncMock(return_value=SimpleNamespace(result="NO", lines=[]))
        await client.get_message("INBOX", "42")
        client._client.uid.assert_awaited_once_with("fetch", "42", "BODY.PEEK[]")

    async def test_list_messages_uses_peek(self, monkeypatch):
        client = _make_client(monkeypatch)
        client._client.examine = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"3 EXISTS"]))
        client._client.fetch = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[]))
        await client.list_messages("INBOX")
        parts = client._client.fetch.call_args[0][1]
        assert "BODY.PEEK[" in parts
        assert "BODY[" not in parts

    async def test_failed_examine_does_not_read_previous_mailbox(self, monkeypatch):
        client = _make_client(monkeypatch)
        client._client.examine = AsyncMock(return_value=SimpleNamespace(result="NO", lines=[]))
        with pytest.raises(LookupError):
            await client.get_message("Folders/Missing", "42")
        client._client.uid.assert_not_called()
        client._client.fetch.assert_not_called()

    async def test_status_quotes_mailbox(self, monkeypatch):
        client = _make_client(monkeypatch)
        client._client.status = AsyncMock(return_value=SimpleNamespace(
            result="OK", lines=[b'"Folders/My Stuff" (MESSAGES 7 UNSEEN 2)', b"STATUS completed"]))
        result = await client.get_mailbox_status("Folders/My Stuff")
        client._client.status.assert_awaited_once_with('"Folders/My Stuff"', "(MESSAGES UNSEEN)")
        assert result == {"messages": 7, "unseen": 2}


class TestListMessagesPaging:
    @pytest.mark.parametrize("page,page_size", [(0, 20), (-1, 20), (1, 0), (1, -5), (1, 101)])
    async def test_rejects_bad_paging(self, monkeypatch, page, page_size):
        client = _make_client(monkeypatch)
        with pytest.raises(ValueError):
            await client.list_messages("INBOX", page=page, page_size=page_size)

    async def test_page_past_the_end_is_empty(self, monkeypatch):
        client = _make_client(monkeypatch)
        client._client.examine = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"3 EXISTS"]))
        result = await client.list_messages("INBOX", page=5, page_size=20)
        assert result["messages"] == []
        assert result["total"] == 3
        client._client.fetch.assert_not_called()


class TestOutgoingCommandGuard:
    """Last line of defence: only single-line, read-only commands may be sent."""

    @pytest.mark.parametrize("line", [
        "A1 CAPABILITY",
        'A2 LOGIN user@proton.me "pw"',
        "A3 NOOP",
        'A4 LIST "" *',
        'A5 STATUS "INBOX" (MESSAGES UNSEEN)',
        'A6 EXAMINE "Folders/My Stuff"',
        "A7 SEARCH CHARSET utf-8 UNSEEN",
        "A8 FETCH 1:3 (UID FLAGS BODY.PEEK[HEADER.FIELDS (DATE FROM)])",
        "A9 UID FETCH 5 BODY.PEEK[]",
        "A10 LOGOUT",
    ])
    def test_allows_read_commands(self, line):
        _check_outgoing_line(line)

    @pytest.mark.parametrize("line", [
        "A1 SELECT INBOX",
        "A1 UID STORE 5 +FLAGS (\\Deleted)",
        "A1 STORE 5 +FLAGS (\\Seen)",
        "A1 EXPUNGE",
        "A1 UID EXPUNGE 5",
        "A1 UID COPY 5 Trash",
        "A1 UID MOVE 5 Trash",
        "A1 APPEND INBOX {10}",
        "A1 CREATE x",
        "A1 DELETE x",
        "A1 RENAME a b",
        "A1 SUBSCRIBE x",
        "A1 CLOSE",
        "A1 IDLE",
        "DONE",
        "A1 UID",
        "A1",
        "",
    ])
    def test_blocks_everything_else(self, line):
        with pytest.raises(ValueError):
            _check_outgoing_line(line)

    @pytest.mark.parametrize("line", [
        "A1 SEARCH SINCE 01-Jan-2026\r\nZZ99 DELETE x",
        "A1 NOOP\nA2 DELETE x",
        "A1 NOOP\r",
    ])
    def test_blocks_multi_line(self, line):
        with pytest.raises(ValueError):
            _check_outgoing_line(line)

    def test_error_never_echoes_the_line(self):
        with pytest.raises(ValueError) as excinfo:
            _check_outgoing_line('A1 DELETE "s3cret-value"')
        assert "s3cret-value" not in str(excinfo.value)

    def test_no_write_command_is_allowed(self):
        writes = {"SELECT", "STORE", "EXPUNGE", "COPY", "MOVE", "APPEND", "CREATE",
                  "DELETE", "RENAME", "SUBSCRIBE", "UNSUBSCRIBE", "CLOSE", "IDLE", "AUTHENTICATE"}
        assert not (writes & _ALLOWED_COMMANDS)

    def test_guard_wraps_protocol_send(self):
        sent = []
        protocol = SimpleNamespace(send=lambda line, scrub=None: sent.append((line, scrub)))
        client = SimpleNamespace(protocol=protocol)
        _install_readonly_guard(client)

        client.protocol.send("A1 NOOP")
        client.protocol.send('A2 LOGIN u "p"', scrub="p")
        with pytest.raises(ValueError):
            client.protocol.send("A3 EXPUNGE")
        with pytest.raises(ValueError):
            client.protocol.send("A4 NOOP\r\nA5 EXPUNGE")

        assert sent == [("A1 NOOP", None), ('A2 LOGIN u "p"', "p")]

    def test_guard_fails_closed_without_send_hook(self):
        with pytest.raises(RuntimeError):
            _install_readonly_guard(SimpleNamespace(protocol=SimpleNamespace()))
        with pytest.raises(RuntimeError):
            _install_readonly_guard(SimpleNamespace())

    async def test_connect_installs_guard_on_real_client(self, monkeypatch):
        """connect() must guard the aioimaplib client before anything is sent."""
        client = _make_client(monkeypatch)
        client._client = None
        sent = []
        fake = MagicMock()
        fake.protocol.send = lambda line, scrub=None: sent.append(line)
        fake.wait_hello_from_server = AsyncMock()
        fake.login = AsyncMock(return_value=OK)
        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=fake):
            await client.connect()
        with pytest.raises(ValueError):
            fake.protocol.send("A1 EXPUNGE")
        fake.protocol.send("A2 NOOP")
        assert sent == ["A2 NOOP"]

    async def test_rejected_login_raises(self, monkeypatch):
        client = _make_client(monkeypatch)
        client._client = None
        fake = MagicMock()
        fake.wait_hello_from_server = AsyncMock()
        fake.login = AsyncMock(return_value=SimpleNamespace(result="NO", lines=[]))
        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=fake):
            with pytest.raises(ConnectionError):
                await client.connect()
        assert client._client is None


class TestAllowedMailboxes:
    """Optional PROTONMAIL_ALLOWED_MAILBOXES restricts which folders can be read."""

    async def test_unrestricted_by_default(self, monkeypatch):
        client = _make_client(monkeypatch)
        client._client.uid = AsyncMock(return_value=SimpleNamespace(result="NO", lines=[]))
        await client.get_message("Sent", "1")
        client._client.examine.assert_awaited_once_with('"Sent"')

    @pytest.mark.parametrize("call", [
        lambda c: c.get_message("INBOX", "1"),
        lambda c: c.get_message_headers("Sent", "1"),
        lambda c: c.list_messages("All Mail"),
        lambda c: c.search_messages("Folders/Private", unseen=True),
        lambda c: c.get_mailbox_status("Labels/Other"),
        lambda c: c.get_message("labels/claude", "1"),
    ])
    async def test_other_mailboxes_are_refused_before_any_command(self, monkeypatch, call):
        client = _make_client(monkeypatch, allowed="Labels/Claude")
        with pytest.raises(PermissionError):
            await call(client)
        assert client._client.mock_calls == []

    async def test_allowed_mailbox_works(self, monkeypatch):
        client = _make_client(monkeypatch, allowed="Labels/Claude, Folders/My Stuff")
        client._client.uid = AsyncMock(return_value=SimpleNamespace(result="NO", lines=[]))
        await client.get_message("Folders/My Stuff", "1")
        client._client.examine.assert_awaited_once_with('"Folders/My Stuff"')

    async def test_inbox_is_case_insensitive(self, monkeypatch):
        client = _make_client(monkeypatch, allowed="INBOX")
        client._client.uid = AsyncMock(return_value=SimpleNamespace(result="NO", lines=[]))
        await client.get_message("inbox", "1")
        client._client.examine.assert_awaited_once()

    async def test_list_mailboxes_only_shows_allowed(self, monkeypatch):
        client = _make_client(monkeypatch, allowed="Labels/Claude")
        client._client.list = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren) "/" "Sent"',
            b'(\\HasNoChildren) "/" "Labels/Claude"',
            b'(\\HasNoChildren) "/" "Labels/Other"',
            b"LIST completed",
        ]))
        assert await client.list_mailboxes() == [{"name": "Labels/Claude", "type": "label"}]

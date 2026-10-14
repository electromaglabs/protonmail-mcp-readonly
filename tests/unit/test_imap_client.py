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
        with pytest.raises(ValueError, match="Ogiltigt UID"):
            _validate_uid("1:*")

    def test_rejects_injection_attempt(self):
        with pytest.raises(ValueError, match="Ogiltigt UID"):
            _validate_uid("123 STORE")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="Ogiltigt UID"):
            _validate_uid("")

    def test_rejects_negative(self):
        with pytest.raises(ValueError, match="Ogiltigt UID"):
            _validate_uid("-1")


# ---------------------------------------------------------------------------
# _validate_mailbox
# ---------------------------------------------------------------------------
class TestValidateMailbox:
    def test_validate_mailbox_valid(self):
        assert _validate_mailbox("INBOX") == "INBOX"
        assert _validate_mailbox("Folders/Sub") == "Folders/Sub"
        assert _validate_mailbox("Labels/Arbete") == "Labels/Arbete"

    def test_validate_mailbox_allows_wildcard(self):
        # Proton tillåter "*" och "%" i namn; de betyder bara något i LIST-mönster
        assert _validate_mailbox("INBOX*") == "INBOX*"

    def test_validate_mailbox_allows_dotdot(self):
        # Inget filsystem bakom Bridge, så ".." är ett vanligt namn
        assert _validate_mailbox("../etc/passwd") == "../etc/passwd"

    def test_validate_mailbox_rejects_control_chars(self):
        with pytest.raises(ValueError, match="Ogiltigt mailbox-namn"):
            _validate_mailbox("INBOX\x00")
        with pytest.raises(ValueError, match="Ogiltigt mailbox-namn"):
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

    def test_long_whitespace_is_linear(self):
        import time
        start = time.perf_counter()
        _parse_headers(b"Subject: " + b" " * 200_000 + b"x\r\n")
        assert time.perf_counter() - start < 0.5

    def test_folded_header_keeps_continuation(self):
        """En vikt From-rad får inte tappa adressen på fortsättningsraden."""
        raw = (
            b'From: "Microsoft account team"\r\n'
            b" <account-security-noreply@accountprotection.microsoft.com>\r\n"
            b"Subject: Hej\r\n"
        )
        result = _parse_headers(raw)
        assert result["from"] == (
            '"Microsoft account team" '
            "<account-security-noreply@accountprotection.microsoft.com>"
        )
        assert result["subject"] == "Hej"


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
    async def test_list_mailboxes_returns_type_system(self, client):
        """INBOX är en systemmapp (N6: typerna är system/folder/label/container)."""
        client._client.list = AsyncMock(return_value=SimpleNamespace(
            result="OK",
            lines=[
                '(\\HasNoChildren) "/" "INBOX"',
                'command completed',
            ],
        ))
        result = await client.list_mailboxes()
        assert len(result) == 1
        assert result[0] == {"name": "INBOX", "type": "system", "selectable": True, "special_use": None}

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
        assert result[0] == {"name": "Labels/Arbete", "type": "label", "selectable": True, "special_use": None}

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
        assert types["INBOX"] == "system"
        assert types["Sent"] == "system"
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
        with pytest.raises(ValueError, match="Ogiltigt UID"):
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
# IMAPClient.delete_message — UID-validering
# ---------------------------------------------------------------------------
class TestDeleteMessage:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        imap = IMAPClient(settings)
        imap._client = AsyncMock()
        return imap

    @pytest.mark.asyncio
    async def test_rejects_invalid_uid(self, client):
        with pytest.raises(ValueError, match="Ogiltigt UID"):
            await client.delete_message("INBOX", "1:*")

    @pytest.mark.asyncio
    async def test_successful_delete(self, client):
        # Standard är flytt till Trash; UID FETCH kontrollerar först att UID:t finns
        client._client.uid = AsyncMock(return_value=SimpleNamespace(
            result="OK", lines=[b"1 FETCH (UID 42)", b"done"]
        ))
        result = await client.delete_message("INBOX", "42")
        assert result is True
        client._client.uid.assert_awaited_with("move", "42", '"Trash"')
        client._client.expunge.assert_not_called()


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
        mock_new_client.login = AsyncMock()

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
# IMAPClient.create_folder / delete_folder / rename_folder
# ---------------------------------------------------------------------------
class TestFolderManagement:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        settings = Settings()
        imap = IMAPClient(settings)
        imap._client = AsyncMock()
        return imap

    @pytest.mark.asyncio
    async def test_create_folder_ok(self, client):
        client._client.create = AsyncMock(return_value=SimpleNamespace(result="OK"))
        result = await client.create_folder("Folders/NewFolder")
        assert result is True
        client._client.create.assert_awaited_once_with('"Folders/NewFolder"')

    @pytest.mark.asyncio
    async def test_delete_folder_ok(self, client):
        client._client.delete = AsyncMock(return_value=SimpleNamespace(result="OK"))
        result = await client.delete_folder("Folders/OldFolder")
        assert result is True
        client._client.delete.assert_awaited_once_with('"Folders/OldFolder"')

    @pytest.mark.asyncio
    async def test_rename_folder_ok(self, client):
        client._client.rename = AsyncMock(return_value=SimpleNamespace(result="OK"))
        result = await client.rename_folder("Folders/OldName", "Folders/NewName")
        assert result is True
        client._client.rename.assert_awaited_once_with('"Folders/OldName"', '"Folders/NewName"')


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
        client._client.select = AsyncMock(return_value=self._make_select_resp(5))
        client._client.fetch = AsyncMock(return_value=self._make_fetch_resp([1, 2, 3, 4, 5]))

        result = await client.list_messages("INBOX", page=1, page_size=20)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"messages", "total", "page", "pages", "has_more"}
        assert isinstance(result["messages"], list)

    @pytest.mark.asyncio
    async def test_list_messages_page1(self, client):
        """page=1, page_size=5, total=12 → has_more=True, pages=3."""
        client._client.select = AsyncMock(return_value=self._make_select_resp(12))
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
        client._client.select = AsyncMock(return_value=self._make_select_resp(12))
        client._client.fetch = AsyncMock(return_value=self._make_fetch_resp([1, 2]))

        result = await client.list_messages("INBOX", page=3, page_size=5)
        assert result["total"] == 12
        assert result["page"] == 3
        assert result["pages"] == 3
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_messages_empty_mailbox(self, client):
        """Tom mailbox → total=0, pages=0, tom messages-lista."""
        client._client.select = AsyncMock(return_value=self._make_select_resp(0))

        result = await client.list_messages("INBOX", page=1, page_size=20)
        assert isinstance(result, dict)
        assert result["total"] == 0
        assert result["pages"] == 0
        assert result["has_more"] is False
        assert result["messages"] == []


# ---------------------------------------------------------------------------
# Läsning ska inte sätta \Seen, mappnamn citeras, metadata avkodas och sorteras
#
# Givet en inkorg med mejl vars ämnen är RFC 2047-kodade
# När Claude listar eller öppnar mejl
# Så markeras inget som läst, ämnen och avsändare visas avkodade
# och listan är sorterad nyast först (högst UID först)
# ---------------------------------------------------------------------------
class TestReadOnlyAndDecodedListing:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        imap = IMAPClient(Settings())
        imap._client = AsyncMock()
        imap._client.select = AsyncMock(
            return_value=SimpleNamespace(result="OK", lines=["5 EXISTS"])
        )
        return imap

    @staticmethod
    def _fetch_resp(uids: list[int]):
        lines = []
        for uid in uids:
            lines.append(f'1 FETCH (UID {uid} FLAGS () BODY[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)] {{50}}')
            lines.append(bytearray(f"Subject: Mail {uid}\r\nFrom: a@b.com\r\n".encode()))
            lines.append(")")
        return SimpleNamespace(result="OK", lines=lines)

    @pytest.mark.asyncio
    async def test_list_messages_quotes_mailbox_with_brackets(self, client):
        client._client.fetch = AsyncMock(return_value=self._fetch_resp([1]))
        await client.list_messages("Folders/[X]")
        client._client.select.assert_awaited_with('"Folders/[X]"')

    @pytest.mark.asyncio
    async def test_list_messages_uses_body_peek(self, client):
        client._client.fetch = AsyncMock(return_value=self._fetch_resp([1]))
        await client.list_messages("INBOX")
        fetch_items = client._client.fetch.await_args.args[1]
        assert "BODY.PEEK[HEADER.FIELDS" in fetch_items

    @pytest.mark.asyncio
    async def test_get_message_uses_body_peek(self, client):
        client._client.uid = AsyncMock(return_value=SimpleNamespace(
            result="OK", lines=["1 FETCH (BODY[] {5}", bytearray(b"x: y\r\n"), ")"],
        ))
        await client.get_message("INBOX", "42")
        assert client._client.uid.await_args.args[2] == "BODY.PEEK[]"

    @pytest.mark.asyncio
    async def test_list_messages_sorted_newest_uid_first(self, client):
        client._client.fetch = AsyncMock(return_value=self._fetch_resp([3, 5, 1, 4, 2]))
        result = await client.list_messages("INBOX")
        assert [m["uid"] for m in result["messages"]] == ["5", "4", "3", "2", "1"]

    def test_metadata_decodes_encoded_words(self):
        lines = [
            '1 FETCH (UID 7 FLAGS () BODY[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)] {90}',
            bytearray(
                b"Subject: =?utf-8?q?Bli_h=C3=A5llen?=\r\n"
                b"From: =?utf-8?q?Ta=C3=AFme_Smit?= <info@e.wemove.eu>\r\n"
            ),
            ")",
        ]
        msg = _parse_fetch_metadata(lines)[0]
        assert msg["subject"] == "Bli hållen"
        assert msg["from"] == "Taïme Smit <info@e.wemove.eu>"

    def test_metadata_handles_folded_subject(self):
        lines = [
            '1 FETCH (UID 8 FLAGS () BODY[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)] {90}',
            bytearray(b"Subject: Ett langt\r\n amne\r\nFrom: a@b.com\r\n"),
            ")",
        ]
        assert _parse_fetch_metadata(lines)[0]["subject"] == "Ett langt amne"


# ---------------------------------------------------------------------------
# Samtidiga verktygsanrop
#
# Givet att Claude anropar två verktyg parallellt mot samma IMAP-anslutning
# När båda startar innan någon anslutning finns
# Så loggar klienten in en gång och kommandona körs ett i taget
# (annars: "LOGIN illegal in state SELECTED" och SELECT som byter mapp mitt i)
# ---------------------------------------------------------------------------
class TestConcurrentCalls:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        from protonmail_mcp.config import Settings
        return IMAPClient(Settings())

    @pytest.mark.asyncio
    async def test_parallel_calls_login_once_and_do_not_interleave(self, client):
        in_flight = 0
        max_in_flight = 0
        fake = AsyncMock()

        async def slow_select(_mailbox):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return SimpleNamespace(result="OK", lines=["0 EXISTS"])

        async def slow_hello():
            await asyncio.sleep(0.01)

        fake.select = slow_select
        fake.wait_hello_from_server = slow_hello
        fake.uid = AsyncMock(return_value=SimpleNamespace(result="NO", lines=[]))

        with patch("protonmail_mcp.imap_client.aioimaplib.IMAP4", return_value=fake) as ctor:
            await asyncio.gather(
                client.list_messages("INBOX"),
                client.get_message_headers("Sent", "1"),
                client.list_messages("Archive"),
            )

        assert ctor.call_count == 1
        assert fake.login.await_count == 1
        assert max_in_flight == 1

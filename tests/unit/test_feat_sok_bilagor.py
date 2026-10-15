"""Enhetstester för has_attachment i search_messages/search_emails (feat-sok)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient, _attachment_uids
from protonmail_mcp.server import mcp
from protonmail_mcp.tools.search import search_emails
from tests.feat_sok_fakebridge import FakeBridge, FakeMessage
from tests import sdk_support as sdk

_MIXED = "multipart/mixed"


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    fake = FakeBridge()
    imap = IMAPClient(Settings())
    imap._client = fake.client()
    fake.imap = imap
    return fake


def _uids(result):
    return [m["uid"] for m in result["messages"]]


class TestAttachmentUids:
    """Tolkning av FETCH (UID BODYSTRUCTURE) — formatet är Bridges, avläst live."""

    def test_attachment_disposition(self):
        lines = [
            b'5 FETCH (UID 10961 BODYSTRUCTURE (("text" "html" ("charset" "utf-8") NIL NIL '
            b'"quoted-printable" 683 9 NIL NIL NIL NIL)("application" "pdf" ("filename" "A.pdf" '
            b'"name" "A.pdf") "<x>" NIL "base64" 5922206 NIL ("attachment" ("filename" "A.pdf")) '
            b'NIL NIL) "mixed" ("boundary" "b") NIL NIL NIL))',
            b"FETCH completed",
        ]
        assert _attachment_uids(lines) == {"10961"}

    def test_inline_image_is_not_an_attachment(self):
        lines = [
            b'6 FETCH (UID 7 BODYSTRUCTURE (("text" "html" NIL NIL NIL "7bit" 1 1 NIL NIL NIL NIL)'
            b'("image" "png" ("name" "logo.png") "<l>" NIL "base64" 9 NIL ("inline" ("filename" '
            b'"logo.png")) NIL NIL) "mixed" NIL NIL NIL NIL))',
        ]
        assert _attachment_uids(lines) == set()

    def test_file_named_attachment_is_not_a_disposition(self):
        lines = [
            b'6 FETCH (UID 8 BODYSTRUCTURE (("text" "plain" ("name" "attachment") NIL NIL "7bit" 1 1 '
            b'NIL ("inline" ("filename" "attachment")) NIL NIL) "mixed" NIL NIL NIL NIL))',
        ]
        assert _attachment_uids(lines) == set()

    def test_uppercase_disposition(self):
        lines = [b'1 FETCH (BODYSTRUCTURE ("application" "pdf" NIL NIL NIL "base64" 9 NIL '
                 b'("ATTACHMENT" NIL) NIL NIL) UID 9)']
        assert _attachment_uids(lines) == {"9"}

    def test_filename_as_literal(self):
        # Ett filnamn med specialtecken kan komma som literal; raden delas då upp
        lines = [
            b'1 FETCH (UID 12 BODYSTRUCTURE (("text" "html" NIL NIL NIL "7bit" 1 1 NIL NIL NIL NIL)'
            b'("application" "pdf" ("name" {5}',
            bytearray(b'a"b.c'),
            b') NIL NIL "base64" 9 NIL ("attachment" NIL) NIL NIL) "mixed" NIL NIL NIL NIL))',
        ]
        assert _attachment_uids(lines) == {"12"}


class TestSearchHasAttachment:
    def _fill(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, content_type=_MIXED, parts=["text", "attachment"]))
        bridge.add("INBOX", FakeMessage(uid=2, content_type=_MIXED, parts=["text", "inline-bild"]))
        bridge.add("INBOX", FakeMessage(uid=3))

    async def test_true(self, bridge):
        self._fill(bridge)
        assert _uids(await bridge.imap.search_messages("INBOX", has_attachment=True)) == ["1"]

    async def test_false(self, bridge):
        self._fill(bridge)
        assert _uids(await bridge.imap.search_messages("INBOX", has_attachment=False)) == ["3", "2"]

    async def test_true_narrows_on_the_server_to_multipart(self, bridge):
        self._fill(bridge)
        await bridge.imap.search_messages("INBOX", has_attachment=True)
        assert 'HEADER Content-Type "multipart"' in bridge.search_commands[0]

    async def test_bodystructure_only_fetched_for_multipart(self, bridge):
        self._fill(bridge)
        await bridge.imap.search_messages("INBOX", has_attachment=False)
        uid_calls = [c.args for c in bridge.imap._client.uid.call_args_list]
        fetched = {uid for args in uid_calls for uid in args[1].split(",")}
        assert fetched == {"1", "2"}

    async def test_combines_with_subject(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, headers={"Subject": "Avtal"}, content_type=_MIXED,
                                        parts=["text", "attachment"]))
        bridge.add("INBOX", FakeMessage(uid=2, headers={"Subject": "Kvitto"}, content_type=_MIXED,
                                        parts=["text", "attachment"]))
        result = await bridge.imap.search_messages("INBOX", subject="avtal", has_attachment=True)
        assert _uids(result) == ["1"]

    async def test_total_counts_only_attachment_matches(self, bridge):
        for uid in range(1, 6):
            bridge.add("INBOX", FakeMessage(uid=uid, content_type=_MIXED, parts=["text", "attachment"]))
        bridge.add("INBOX", FakeMessage(uid=6))
        result = await bridge.imap.search_messages("INBOX", has_attachment=True, max_results=2)
        assert _uids(result) == ["5", "4"]
        assert result["total"] == 5 and result["has_more"] is True and result["complete"] is True

    async def test_non_bool_is_refused(self, bridge):
        with pytest.raises(ValueError, match="true, false eller null"):
            await bridge.imap.search_messages("INBOX", has_attachment="ja")


class TestTool:
    def test_schema_is_strict_bool(self):
        tool = next(t for t in sdk.list_tools(mcp) if t.name == "search_emails")
        types = {t["type"] for t in tool.parameters["properties"]["has_attachment"]["anyOf"]}
        assert types == {"boolean", "null"}

    async def test_passes_has_attachment(self):
        ctx = MagicMock()
        ctx.request_context.lifespan_context.imap = AsyncMock()
        ctx.request_context.lifespan_context.imap.search_messages.return_value = {
            "messages": [], "total": 0, "has_more": False, "complete": True, "note": None,
        }
        await search_emails(ctx, mailbox="INBOX", has_attachment=False)
        kwargs = ctx.request_context.lifespan_context.imap.search_messages.call_args.kwargs
        assert kwargs["has_attachment"] is False


class TestBeyondLocalWindow:
    """Fler kandidater än det lokala fönstret: äldre kandidater kontrolleras i delar."""

    @pytest.fixture(autouse=True)
    def small_window(self, monkeypatch):
        monkeypatch.setattr("protonmail_mcp.imap_client._LOCAL_SCAN_LIMIT", 2)
        monkeypatch.setattr("protonmail_mcp.imap_client._FETCH_CHUNK_SIZE", 2)

    async def test_older_attachments_are_found_and_result_is_complete(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, content_type=_MIXED, parts=["text", "attachment"]))
        for uid in range(2, 7):
            bridge.add("INBOX", FakeMessage(uid=uid, content_type=_MIXED, parts=["text", "inline-bild"]))
        result = await bridge.imap.search_messages("INBOX", has_attachment=True)
        assert _uids(result) == ["1"]
        assert result["complete"] is True and result["note"] is None

    async def test_stops_when_enough_matches_and_says_so(self, bridge):
        for uid in range(1, 7):
            bridge.add("INBOX", FakeMessage(uid=uid))
        result = await bridge.imap.search_messages("INBOX", has_attachment=False, max_results=1)
        assert _uids(result) == ["6"]
        assert result["has_more"] is True
        assert result["complete"] is False and "undre gräns" in result["note"]

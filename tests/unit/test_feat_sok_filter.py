"""Enhetstester för de nya filtren i search_messages/search_emails (feat-sok)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient, _text_search_criteria
from protonmail_mcp.server import mcp
from protonmail_mcp.tools.search import search_emails
from tests.feat_sok_fakebridge import FakeBridge, FakeMessage
from tests import sdk_support as sdk


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


# ---------------------------------------------------------------------------
# Sökkriterier för TEXT/BODY
# ---------------------------------------------------------------------------
class TestTextSearchCriteria:
    def test_ascii_term_is_sent_as_is(self):
        assert _text_search_criteria("TEXT", "offert", "text") == ['TEXT', '"offert"']

    def test_non_ascii_term_also_searches_quoted_printable(self):
        # Bridge söker i den okodade brödtexten, där "ö" står som =C3=B6
        command = " ".join(_text_search_criteria("BODY", "behöver", "body"))
        assert 'BODY "beh=C3=B6ver"' in command
        assert 'BODY "behöver"' in command
        assert command.startswith("OR ")

    def test_capitalised_variant_of_non_ascii_letter(self):
        # Bridge viker bara ASCII: Ö (=C3=96) och ö (=C3=B6) är olika byte
        command = " ".join(_text_search_criteria("TEXT", "örebro", "text"))
        assert '"=C3=96rebro"' in command
        assert '"=C3=B6rebro"' in command

    def test_or_is_balanced(self):
        criteria = _text_search_criteria("TEXT", "Åsa möte", "text")
        keys = criteria.count("TEXT")
        assert criteria.count("OR") == keys - 1

    def test_decomposed_input_is_normalised(self):
        # macOS skriver ofta "ö" som o + kombinerande trema
        command = " ".join(_text_search_criteria("TEXT", "möte", "text"))
        assert '"m=C3=B6te"' in command

    def test_control_characters_are_refused(self):
        with pytest.raises(ValueError, match="kontrolltecken"):
            _text_search_criteria("TEXT", "a\r\nX LOGOUT", "text")

    def test_quotes_are_escaped(self):
        assert '"s=C3=A4g \\"hej\\""' in _text_search_criteria("TEXT", 'säg "hej"', "text")


# ---------------------------------------------------------------------------
# search_messages mot falsk Bridge
# ---------------------------------------------------------------------------
class TestFlagsAndSize:
    async def test_flagged_true_and_false(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, flags=["\\Flagged"]))
        bridge.add("INBOX", FakeMessage(uid=2))
        assert _uids(await bridge.imap.search_messages("INBOX", flagged=True)) == ["1"]
        assert _uids(await bridge.imap.search_messages("INBOX", flagged=False)) == ["2"]
        assert "FLAGGED" in bridge.search_commands[0]
        assert "UNFLAGGED" in bridge.search_commands[1]

    async def test_answered_true_and_false(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, flags=["\\Answered"]))
        bridge.add("INBOX", FakeMessage(uid=2))
        assert _uids(await bridge.imap.search_messages("INBOX", answered=True)) == ["1"]
        assert _uids(await bridge.imap.search_messages("INBOX", answered=False)) == ["2"]
        assert "UNANSWERED" in bridge.search_commands[1]

    async def test_size_limits(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, size=100))
        bridge.add("INBOX", FakeMessage(uid=2, size=5000))
        assert _uids(await bridge.imap.search_messages("INBOX", larger_than=1000)) == ["2"]
        assert _uids(await bridge.imap.search_messages("INBOX", smaller_than=1000)) == ["1"]
        assert "LARGER 1000" in bridge.search_commands[0]
        assert "SMALLER 1000" in bridge.search_commands[1]

    @pytest.mark.parametrize("value", [-1, True, 1.5, "100"])
    async def test_invalid_size_is_refused_before_search(self, bridge, value):
        bridge.add("INBOX", FakeMessage(uid=1))
        with pytest.raises(ValueError, match="larger_than"):
            await bridge.imap.search_messages("INBOX", larger_than=value)
        assert bridge.search_commands == []


class TestRecipients:
    async def test_to_matches_decoded_display_name(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, headers={"To": "=?utf-8?q?G=C3=B6ran?= <g@example.com>"}))
        bridge.add("INBOX", FakeMessage(uid=2, headers={"To": "anna@example.com"}))
        assert _uids(await bridge.imap.search_messages("INBOX", to_addr="göran")) == ["1"]

    async def test_cc_matches(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, headers={"To": "x@example.com", "Cc": "anna@example.com"}))
        bridge.add("INBOX", FakeMessage(uid=2, headers={"To": "anna@example.com"}))
        assert _uids(await bridge.imap.search_messages("INBOX", cc_addr="anna@")) == ["1"]

    async def test_to_and_from_combine(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, headers={"From": "bo@x", "To": "anna@x"}))
        bridge.add("INBOX", FakeMessage(uid=2, headers={"From": "cilla@x", "To": "anna@x"}))
        assert _uids(await bridge.imap.search_messages("INBOX", from_addr="bo", to_addr="anna")) == ["1"]

    @pytest.mark.parametrize("name", ["to_addr", "cc_addr", "text", "body"])
    async def test_control_characters_are_refused_before_search(self, bridge, name):
        bridge.add("INBOX", FakeMessage(uid=1))
        with pytest.raises(ValueError, match="kontrolltecken"):
            await bridge.imap.search_messages("INBOX", **{name: "x\r\nA1 LOGOUT"})
        assert bridge.search_commands == []


class TestBodyText:
    async def test_body_with_non_ascii_finds_quoted_printable_body(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, body="Vi behöver offerten"))
        bridge.add("INBOX", FakeMessage(uid=2, body="Inget här"))
        assert _uids(await bridge.imap.search_messages("INBOX", body="behöver")) == ["1"]

    async def test_body_ignores_headers(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, headers={"Subject": "offert"}, body="hej"))
        assert _uids(await bridge.imap.search_messages("INBOX", body="offert")) == []

    async def test_text_includes_headers(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, headers={"Subject": "offert"}, body="hej"))
        assert _uids(await bridge.imap.search_messages("INBOX", text="offert")) == ["1"]

    async def test_text_with_capitalised_non_ascii(self, bridge):
        bridge.add("INBOX", FakeMessage(uid=1, body="Hälsningar från Örebro"))
        assert _uids(await bridge.imap.search_messages("INBOX", text="örebro")) == ["1"]


# ---------------------------------------------------------------------------
# Verktyget
# ---------------------------------------------------------------------------
def _schema():
    tool = next(t for t in sdk.list_tools(mcp) if t.name == "search_emails")
    return tool.parameters["properties"]


class TestToolSchema:
    def test_new_string_filters_are_optional_strings(self):
        props = _schema()
        for name in ("to_addr", "cc_addr", "text", "body"):
            assert props[name]["anyOf"] == [{"type": "string"}, {"type": "null"}], name

    def test_new_bool_filters(self):
        props = _schema()
        for name in ("flagged", "answered"):
            types = {t["type"] for t in props[name]["anyOf"]}
            assert types == {"boolean", "null"}, name

    def test_size_filters_are_non_negative_integers(self):
        props = _schema()
        for name in ("larger_than", "smaller_than"):
            integer = next(t for t in props[name]["anyOf"] if t["type"] == "integer")
            assert integer["minimum"] == 0, name


class TestToolDelegation:
    @pytest.fixture
    def ctx(self):
        ctx = MagicMock()
        ctx.request_context.lifespan_context.imap = AsyncMock()
        ctx.request_context.lifespan_context.imap.search_messages.return_value = {
            "messages": [], "total": 0, "has_more": False, "complete": True, "note": None,
        }
        return ctx

    async def test_passes_new_filters(self, ctx):
        await search_emails(
            ctx, mailbox="INBOX", to_addr="a", cc_addr="b", text="c", body="d",
            flagged=True, answered=False, larger_than=10, smaller_than=20,
        )
        kwargs = ctx.request_context.lifespan_context.imap.search_messages.call_args.kwargs
        assert kwargs["to_addr"] == "a" and kwargs["cc_addr"] == "b"
        assert kwargs["text"] == "c" and kwargs["body"] == "d"
        assert kwargs["flagged"] is True and kwargs["answered"] is False
        assert kwargs["larger_than"] == 10 and kwargs["smaller_than"] == 20

    async def test_unset_new_filters_are_not_passed(self, ctx):
        await search_emails(ctx, mailbox="INBOX")
        kwargs = ctx.request_context.lifespan_context.imap.search_messages.call_args.kwargs
        assert not {"to_addr", "text", "flagged", "larger_than"} & kwargs.keys()

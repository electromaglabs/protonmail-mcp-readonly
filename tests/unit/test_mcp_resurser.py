"""Enhetstester: resurs-URI:er och resurserna (mcp-resurser)."""
import asyncio
import json

import pytest
from pydantic import AnyUrl

from protonmail_mcp import resources
from tests.mcp_resurser_support import client_session, fake_imap, read_or_error, text_of_resource


class TestMailboxUri:
    @pytest.mark.parametrize(
        "name, uri",
        [
            ("INBOX", "mailbox://INBOX"),
            ("All Mail", "mailbox://All%20Mail"),
            ("Labels/Näs Samfällighet", "mailbox://Labels%2FN%C3%A4s%20Samf%C3%A4llighet"),
            ("Folders/A/B", "mailbox://Folders%2FA%2FB"),
            ("Labels/a\\/b", "mailbox://Labels%2Fa%5C%2Fb"),
            ("x&y%z~_.-", "mailbox://x%26y%25z~_.-"),
        ],
    )
    def test_percent_encodes_everything_but_unreserved(self, name, uri):
        assert resources.mailbox_uri(name) == uri

    @pytest.mark.parametrize("name", ["INBOX", "Labels/Näs Samfällighet", "Folders/A/B", "a%2Fb", "日本"])
    def test_round_trip(self, name):
        assert resources.parse_mailbox_uri(resources.mailbox_uri(name)) == name

    def test_uri_survives_pydantic_anyurl(self):
        # Klient och server skickar URI:n som AnyUrl; den får inte normaliseras om
        for name in ("INBOX", "Inbox", "Labels/Näs Samfällighet", "Folders/A/B"):
            uri = resources.mailbox_uri(name)
            assert str(AnyUrl(uri)) == uri

    def test_unencoded_slash_is_accepted(self):
        assert resources.parse_mailbox_uri("mailbox://Folders/A/B") == "Folders/A/B"

    def test_lowercase_percent_encoding_is_accepted(self):
        assert resources.parse_mailbox_uri("mailbox://N%c3%a4s") == "Näs"


class TestEmailUri:
    def test_encodes_mailbox_and_uid(self):
        assert resources.email_uri("Folders/A/B", "42") == "email://Folders%2FA%2FB/42"

    def test_round_trip(self):
        uri = resources.email_uri("Labels/Näs Samfällighet", "7")
        assert resources.parse_email_uri(uri) == ("Labels/Näs Samfällighet", "7")

    def test_unencoded_slashes_in_mailbox(self):
        assert resources.parse_email_uri("email://Folders/A/B/42") == ("Folders/A/B", "42")


class TestCanonicalUri:
    @pytest.mark.parametrize(
        "uri, canonical",
        [
            ("mailbox://Folders/A/B", "mailbox://Folders%2FA%2FB"),
            ("mailbox://N%c3%a4s", "mailbox://N%C3%A4s"),
            ("email://Folders/A/B/42", "email://Folders%2FA%2FB/42"),
            ("mailboxes://", "mailboxes://"),
            ("mailbox://INBOX", "mailbox://INBOX"),
        ],
    )
    def test_canonical_form(self, uri, canonical):
        assert resources.canonical_uri(uri) == canonical

    @pytest.mark.parametrize("uri", ["file:///etc/passwd", "mailbox://", "email://INBOX", "email://INBOX/abc"])
    def test_unknown_or_invalid_uri_is_refused(self, uri):
        with pytest.raises(ValueError):
            resources.canonical_uri(uri)


def _read(monkeypatch, uri, imap=None):
    imap = imap or fake_imap()

    async def run():
        async with client_session(monkeypatch, imap=imap) as session:
            return await session.read_resource(AnyUrl(uri))

    return asyncio.run(run()), imap


def _read_error(monkeypatch, uri, imap=None):
    imap = imap or fake_imap()

    async def run():
        async with client_session(monkeypatch, imap=imap) as session:
            return await read_or_error(session, uri)

    text, error = asyncio.run(run())
    assert error is not None, f"läsningen lyckades: {text}"
    return error


class TestResources:
    def test_contents_are_json(self, monkeypatch):
        result, _ = _read(monkeypatch, "mailboxes://")
        assert result.contents[0].mimeType == "application/json"
        json.loads(text_of_resource(result))

    def test_mailbox_resource_reads_unencoded_slashes_too(self, monkeypatch):
        _, imap = _read(monkeypatch, "mailbox://Folders/A/B")
        imap.get_mailbox_status.assert_awaited_with("Folders/A/B")

    def test_mailbox_resource_has_uri_of_itself(self, monkeypatch):
        result, _ = _read(monkeypatch, "mailbox://Folders%2FA%2FB")
        assert json.loads(text_of_resource(result))["uri"] == "mailbox://Folders%2FA%2FB"

    def test_email_resource_uses_text_and_limited_length(self, monkeypatch):
        result, imap = _read(monkeypatch, "email://INBOX/42")
        data = json.loads(text_of_resource(result))
        assert data["mailbox"] == "INBOX"
        assert 1000 <= resources.EMAIL_MAX_LENGTH <= 100_000

    def test_number_in_uid_position_must_be_digits(self, monkeypatch):
        message = _read_error(monkeypatch, "email://INBOX/1:*")
        assert "Ogiltigt UID" in message

    def test_too_long_mailbox_name(self, monkeypatch):
        message = _read_error(monkeypatch, resources.mailbox_uri("x" * 256))
        assert "255" in message

    def test_control_character_in_mailbox_name(self, monkeypatch):
        imap = fake_imap()
        message = _read_error(monkeypatch, "mailbox://IN%0D%0ABOX", imap)
        assert "mailbox" in message.lower()
        assert not imap.method_calls

    def test_unexpected_error_is_not_leaked(self, monkeypatch):
        imap = fake_imap()
        imap.list_mailboxes.side_effect = RuntimeError("intern detalj")
        message = _read_error(monkeypatch, "mailboxes://", imap)
        assert "Oväntat fel" in message
        assert "intern detalj" not in message

    def test_templates_describe_the_encoding(self, monkeypatch):
        async def run():
            async with client_session(monkeypatch) as session:
                return await session.list_resource_templates()

        templates = asyncio.run(run()).resourceTemplates
        by_uri = {t.uriTemplate: t for t in templates}
        for template in ("mailbox://{mailbox}", "email://{mailbox}/{uid}"):
            assert "%2F" in by_uri[template].description
            assert by_uri[template].mimeType == "application/json"

    def test_email_template_says_content_is_untrusted(self, monkeypatch):
        async def run():
            async with client_session(monkeypatch) as session:
                return await session.list_resource_templates()

        templates = asyncio.run(run()).resourceTemplates
        email = next(t for t in templates if t.uriTemplate == "email://{mailbox}/{uid}")
        assert "opålitlig" in email.description
        assert "läst" in email.description

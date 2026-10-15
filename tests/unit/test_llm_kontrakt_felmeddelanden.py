"""Enhetstester: tools._errors gör om interna undantag till begripliga fel (llm-kontrakt)."""
import asyncio
import logging
import socket
from types import SimpleNamespace

import aioimaplib
import aiosmtplib
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from protonmail_mcp import config
from protonmail_mcp.imap_client import IMAPAuthenticationError
from protonmail_mcp.smtp_client import SMTPPartialDeliveryError
from protonmail_mcp.tools import _errors
from protonmail_mcp.tools._errors import describe_error, with_error_messages


def describe(exc, *, open_world=False):
    return describe_error(exc, tool_name="verktyget", open_world=open_world)


class TestValueError:
    def test_text_is_kept(self):
        assert describe(ValueError("Inget meddelande med UID 9 i INBOX.")) == "Inget meddelande med UID 9 i INBOX."

    def test_tool_error_is_kept(self):
        assert describe(ToolError("redan formulerat")) == "redan formulerat"

    def test_unicode_error_is_not_shown_as_is(self):
        exc = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        assert "Oväntat fel" in describe(exc)


class TestConnection:
    @pytest.mark.parametrize("exc", [
        ConnectionRefusedError(61, "Connect call failed"),
        ConnectionResetError("Connection lost"),
        ConnectionError("Anslutningen till ProtonMail Bridge bröts under SELECT"),
        TimeoutError(),
        asyncio.TimeoutError(),
        aioimaplib.Abort("socket error"),
        aioimaplib.CommandTimeout("SEARCH"),
        aioimaplib.AioImapException("protokollfel"),
        aiosmtplib.SMTPConnectError("Error connecting to 127.0.0.1 on port 1026"),
        aiosmtplib.SMTPServerDisconnected("Unexpected EOF"),
        aiosmtplib.SMTPReadTimeoutError("Timed out waiting for server response"),
        socket.gaierror(8, "nodename nor servname provided"),
    ], ids=lambda e: type(e).__name__)
    def test_says_bridge_unreachable(self, exc):
        text = describe(exc)
        assert text.startswith("Kan inte nå ProtonMail Bridge")
        assert "körs Bridge?" in text
        assert "Traceback" not in text

    def test_detail_is_included_on_one_line(self):
        text = describe(ConnectionError("rad ett\nrad två"))
        assert "rad ett rad två" in text

    def test_timeout_without_text_names_the_type(self):
        assert "TimeoutError" in describe(asyncio.TimeoutError())

    def test_sending_tool_warns_mail_may_have_been_sent(self):
        text = describe(aiosmtplib.SMTPServerDisconnected("EOF"), open_world=True)
        assert "kan ha skickats" in text and "Sent" in text

    def test_reading_tool_does_not_talk_about_sent(self):
        assert "Sent" not in describe(ConnectionError("x"))


class TestAuthentication:
    @pytest.mark.parametrize("exc", [
        IMAPAuthenticationError("Inloggningen mot ProtonMail Bridge misslyckades (NO)"),
        aiosmtplib.SMTPAuthenticationError(535, "5.7.8 authentication failed"),
    ], ids=["imap", "smtp"])
    def test_points_to_username_and_bridge_password(self, exc):
        text = describe(exc)
        assert "PROTONMAIL_USERNAME" in text
        assert "PROTONMAIL_PASSWORD" in text and "Bridge-lösenord" in text

    def test_smtp_reply_is_included(self):
        assert "535" in describe(aiosmtplib.SMTPAuthenticationError(535, "authentication failed"))


class TestSmtpRefusals:
    def test_partial_delivery_lists_who_got_it_and_who_did_not(self):
        exc = SMTPPartialDeliveryError(
            refused={"b@x.se": (550, "No such user"), "c@x.se": (552, "Mailbox full")},
            delivered=["a@x.se"],
        )
        text = describe(exc, open_world=True)
        assert "Fick mejlet: a@x.se" in text
        assert "b@x.se (550 No such user)" in text and "c@x.se (552 Mailbox full)" in text
        assert "Skicka inte om" in text

    def test_all_recipients_refused(self):
        exc = aiosmtplib.SMTPRecipientsRefused([
            aiosmtplib.SMTPRecipientRefused(550, "No such user", "b@x.se"),
        ])
        text = describe(exc, open_world=True)
        assert "b@x.se" in text and "550" in text
        assert "Inget mejl skickades" in text

    def test_other_smtp_reply(self):
        text = describe(aiosmtplib.SMTPDataError(554, "Message rejected"), open_world=True)
        assert "554 Message rejected" in text


class TestUnexpected:
    def test_generic_text_without_internals(self):
        text = describe(RuntimeError("intern detalj"))
        assert "Oväntat fel i verktyget" in text and "RuntimeError" in text
        assert "intern detalj" not in text

    def test_logged_with_traceback(self, caplog):
        caplog.set_level(logging.ERROR)
        try:
            raise KeyError("nyckel")
        except KeyError as exc:
            describe(exc)
        message = caplog.records[-1].getMessage()
        assert "verktyget" in message and "Traceback" in message and "KeyError" in message

    def test_password_never_logged_or_returned(self, caplog, monkeypatch):
        monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(password="hemligt-123"))
        caplog.set_level(logging.ERROR)
        try:
            raise RuntimeError("login med hemligt-123 misslyckades")
        except RuntimeError as exc:
            text = describe(exc)
        assert "hemligt-123" not in text
        assert "hemligt-123" not in caplog.text
        assert "***" in caplog.text

    def test_password_scrubbed_from_kept_texts(self, monkeypatch):
        monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(password="hemligt-123"))
        assert "hemligt-123" not in describe(ValueError("fel: hemligt-123"))
        assert "hemligt-123" not in describe(ConnectionError("fel: hemligt-123"))

    def test_missing_settings_does_not_break_error_handling(self, monkeypatch):
        def broken():
            raise RuntimeError("ingen konfiguration")

        monkeypatch.setattr(config, "get_settings", broken)
        assert describe(ValueError("x")) == "x"


class TestWrapper:
    async def test_success_passes_through(self):
        async def fn(ctx, x: int) -> int:
            return x + 1

        assert await with_error_messages(fn, "fn", open_world=False)(None, x=1) == 2

    async def test_error_becomes_tool_error_with_text(self):
        async def fn(ctx):
            raise ConnectionRefusedError(61, "refused")

        with pytest.raises(ToolError) as excinfo:
            await with_error_messages(fn, "fn", open_world=False)(None)
        assert str(excinfo.value).startswith("Kan inte nå ProtonMail Bridge")

    async def test_cancellation_is_not_rewritten(self):
        async def fn(ctx):
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await with_error_messages(fn, "fn", open_world=False)(None)

    def test_signature_is_kept_for_fastmcp(self):
        import inspect

        async def fn(ctx, uid: str, mailbox: str = "INBOX") -> dict:
            """Dokumentation."""
            return {}

        wrapped = with_error_messages(fn, "fn", open_world=False)
        assert inspect.signature(wrapped) == inspect.signature(fn)
        assert wrapped.__doc__ == "Dokumentation."
        assert inspect.iscoroutinefunction(wrapped)


def test_every_registered_tool_is_wrapped():
    from protonmail_mcp.server import mcp, register_tools

    register_tools()
    for tool in mcp._tool_manager.list_tools():
        assert getattr(tool.fn, "_error_messages", False), tool.name


def test_module_has_logger():
    assert _errors.logger.name == "protonmail_mcp.tools._errors"


def test_imap_clients_own_unreachable_text_is_not_repeated():
    exc = ConnectionError(
        "Kan inte nå ProtonMail Bridge på 127.0.0.1:1143 — körs Bridge? ([Errno 61] Connect call failed)"
    )
    text = describe(exc)
    assert text.startswith("Kan inte nå ProtonMail Bridge på 127.0.0.1:1143")
    assert text.count("Kan inte nå ProtonMail Bridge") == 1
    assert text.count("körs Bridge?") == 1
    assert "Starta Bridge-appen" in text

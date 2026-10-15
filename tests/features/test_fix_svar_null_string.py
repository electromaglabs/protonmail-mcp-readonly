"""BDD-steg för fix_svar_null_string.feature."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.server import mcp
from tests import sdk_support as sdk
from protonmail_mcp.tools import reply, send  # noqa: F401 — registrerar verktygen

scenarios("fix_svar_null_string.feature")


@given("en MCP-klient med attrapp för SMTP", target_fixture="ctx")
def ctx():
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()
    app.imap.get_message.return_value = (
        b"From: a@x.se\r\nTo: me@proton.me\r\nSubject: s\r\n\r\nhej\r\n"
    )
    app.smtp = AsyncMock()
    app.smtp.send_email.return_value = True
    return ctx


@when(parsers.parse('jag anropar verktyget send_email med HTML-texten "{html}"'))
def call_send(ctx, html):
    args = {"to": "b@x.se", "subject": "s", "body": "b", "body_html": html}
    asyncio.run(sdk.get_tool(mcp, "send_email").run(args, context=ctx))


@when(parsers.parse('jag anropar verktyget reply_to_email med HTML-texten "{html}"'))
def call_reply(ctx, html):
    args = {"uid": "1", "mailbox": "INBOX", "body": "b", "body_html": html}
    asyncio.run(sdk.get_tool(mcp, "reply_to_email").run(args, context=ctx))


def _html(ctx):
    return ctx.request_context.lifespan_context.smtp.send_email.call_args.kwargs["body_html"]


@then(parsers.parse('ska SMTP-klienten få HTML-texten "{html}"'))
def got_html(ctx, html):
    assert _html(ctx) == html


@then(parsers.parse('ska SMTP-klientens HTML-text börja med "{html}"'))
def html_starts(ctx, html):
    assert _html(ctx) is not None and _html(ctx).startswith(html)

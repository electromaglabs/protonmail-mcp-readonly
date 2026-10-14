"""BDD-steg för fix_svar_svar.feature och fix_svar_vidarebefordra.feature.

Verktygen körs mot den riktiga SMTPClient; bara IMAP-hämtningen och
aiosmtplib är attrapper, så stegen granskar det som skulle gått ut på tråden.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.reply import reply_to_email
from tests.fix_svar_support import capture_smtp, header_addresses, make_client

scenarios("fix_svar_svar.feature")


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@pytest.fixture
def captured():
    with capture_smtp() as c:
        yield c


@pytest.fixture
def mailbox():
    """(mapp, uid) -> rått meddelande."""
    return {}


@pytest.fixture
def outcome():
    return {}


@given(parsers.parse('mitt konto är "{account}"'), target_fixture="ctx")
def account_ctx(account, mailbox):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()

    async def get_message(folder, uid):
        return mailbox.get((folder, uid))

    app.imap.get_message.side_effect = get_message
    app.smtp = make_client(account)
    return ctx


@given(parsers.parse('ett mejl med UID "{uid}" från "{sender}" med ämnet "{subject}"'))
def simple_message(mailbox, uid, sender, subject):
    mailbox[("INBOX", uid)] = (
        f"From: {sender}\r\n"
        "To: me@proton.me\r\n"
        f"Subject: {subject}\r\n"
        "Date: Mon, 12 Oct 2026 09:30:00 +0200\r\n"
        f"Message-ID: <orig-{uid}@example.se>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Originaltext\r\n"
    ).encode("utf-8")


def _run(outcome, coro):
    try:
        outcome["result"] = asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001 — scenariot granskar felet
        outcome["error"] = exc


@when(parsers.re(r'jag svarar på mejlet med UID "(?P<uid>[^"]+)" med texten "(?P<text>[^"]*)"'))
def reply(ctx, captured, outcome, uid, text):
    _run(outcome, reply_to_email(ctx, uid=uid, body=text))


@then(parsers.parse('ska svarets ämne vara "{subject}"'))
def reply_subject(captured, outcome, subject):
    assert "error" not in outcome, outcome.get("error")
    assert str(captured.parsed["Subject"]) == subject

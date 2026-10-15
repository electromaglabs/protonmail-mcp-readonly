"""BDD: svar och svarsutkast på ett mejl till sig själv (L4)."""
import asyncio
import email
import email.policy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.drafts import create_reply_draft
from protonmail_mcp.tools.reply import reply_to_email
from tests.fix_svar_support import KONTO, capture_smtp, header_addresses, make_client

scenarios("efterfix_live_svar.feature")


@pytest.fixture
def svar():
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()
    app.smtp = make_client(KONTO)
    return {"ctx": ctx, "app": app}


@given(parsers.parse('att mejlet med UID "{uid}" i "{mailbox}" är från "{sender}" till "{to}"'))
def original(svar, uid, mailbox, sender, to):
    raw = (
        # X-Pm-Origin: internal som Bridge sätter på egna mejl (efterfix-slut)
        f"From: {sender}\r\nTo: {to}\r\nX-Pm-Origin: internal\r\n"
        "Subject: Påminnelse\r\nMessage-ID: <p@proton.me>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\nKom ihåg\r\n"
    ).encode()
    svar["app"].imap.get_message.return_value = raw


@when(parsers.parse('jag svarar på UID "{uid}" i "{mailbox}"'))
def reply(svar, uid, mailbox):
    with capture_smtp() as cap:
        asyncio.run(reply_to_email(svar["ctx"], uid=uid, mailbox=mailbox, body="Svar"))
    svar["sent"] = cap.parsed
    svar["recipients"] = cap.recipients


@when(parsers.parse('jag skapar ett svarsutkast på UID "{uid}" i "{mailbox}"'))
def reply_draft(svar, uid, mailbox):
    saved = {}

    async def fake_append(imap, message, message_id):
        saved["raw"] = message
        return "9"

    with patch("protonmail_mcp.tools.drafts.imap_drafts.append_draft", side_effect=fake_append):
        asyncio.run(create_reply_draft(svar["ctx"], uid=uid, mailbox=mailbox, body="Svar"))
    svar["draft"] = email.message_from_bytes(saved["raw"], policy=email.policy.default)


@then(parsers.parse('ska svaret skickas till "{addr}"'))
def sent_to(svar, addr):
    assert [a for _, a in header_addresses(svar["sent"], "To")] == [addr]
    assert svar["recipients"] == [addr]


@then(parsers.parse('ska svaret ha ämnet "{subject}"'))
def subject(svar, subject):
    assert str(svar["sent"]["Subject"]) == subject


@then(parsers.parse('ska utkastet ha mottagaren "{addr}"'))
def draft_to(svar, addr):
    assert [a for _, a in header_addresses(svar["draft"], "To")] == [addr]

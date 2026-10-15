"""BDD: svar på ett förfalskat mejl med From = det egna kontot (säkerhetsnotering i granskning 5)."""
import asyncio
from unittest.mock import AsyncMock

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.reply import reply_to_email
from tests.fix_svar_support import capture_smtp, header_addresses, make_client as make_smtp

scenarios("efterfix_slut_svar.feature")


@given(parsers.parse('mitt konto är "{account}"'))
def account(mock_ctx, bridge, account):
    app = mock_ctx.request_context.lifespan_context
    app.smtp = make_smtp(account)
    app.imap.get_message = AsyncMock()


def _raw(sender: str, to: str, *extra: str) -> bytes:
    lines = [f"From: {sender}", f"To: {to}", *extra, "Subject: Faktura", "Message-ID: <f@x>", "", "Hej"]
    return "\r\n".join(lines).encode()


@given(parsers.parse('att mejlet med UID "{uid}" i "{mailbox}" är från "{sender}" till "{to}" och märkt "{header}"'))
def marked(mock_ctx, uid, mailbox, sender, to, header):
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = _raw(sender, to, header)


@given(parsers.parse(
    'att mejlet med UID "{uid}" i "{mailbox}" är från "{sender}" till "{to}" och samma Proton-mejl finns i Sent'
))
def in_sent(mock_ctx, bridge, uid, mailbox, sender, to):
    key = "<mine@proton.me>"
    bridge.put("Sent", "1", key)
    raw = _raw(sender, to, f"X-Pm-Internal-Id: {bridge.internal_id(key)}")
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw


@when(parsers.parse('jag svarar på UID "{uid}" i "{mailbox}"'))
def reply(mock_ctx, bridge, uid, mailbox):
    with capture_smtp() as cap:
        asyncio.run(reply_to_email(mock_ctx, uid=uid, mailbox=mailbox, body="Svar"))
    bridge.result = [a for _, a in header_addresses(cap.parsed, "To")], cap.recipients


@then(parsers.parse('ska svaret skickas till "{addr}"'))
def sent_to(bridge, addr):
    to, rcpt = bridge.result
    assert to == [addr] and rcpt == [addr], bridge.result


@then(parsers.parse('ska svaret inte skickas till "{addr}"'))
def not_sent_to(bridge, addr):
    to, rcpt = bridge.result
    assert addr not in to and addr not in rcpt, bridge.result

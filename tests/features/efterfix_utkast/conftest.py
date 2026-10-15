"""Gemensamma steg för utkastscenarierna (efterfix-utkast).

Verktygen körs mot den riktiga IMAPClient och SMTPClient; bara aioimaplib
(låtsas-Bridge med riktiga meddelanden, tests/feat_utkast_bridge.py) och
aiosmtplib är attrapper, så stegen granskar både det som hamnar i Drafts och
det som går ut på tråden.
"""
import asyncio
from email.message import EmailMessage
from unittest.mock import MagicMock

import pytest
from pytest_bdd import given, parsers, then

from tests.feat_utkast_bridge import make_imap
from tests.fix_svar_support import capture_smtp, make_client

PDF = b"%PDF-1.4 fejk offert"


@pytest.fixture
def captured():
    with capture_smtp() as c:
        yield c


@pytest.fixture
def outcome():
    return {}


@pytest.fixture
def bridge_pair():
    return make_imap()


@pytest.fixture
def bridge(bridge_pair):
    return bridge_pair[1]


def run(outcome, coro):
    try:
        outcome["result"] = asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001 — scenariot granskar felet
        outcome["error"] = exc


def latest_draft_uid(bridge) -> int:
    return max(bridge.messages("Drafts"))


def latest_draft(bridge):
    return bridge.parsed("Drafts", latest_draft_uid(bridge))


# --- Given -------------------------------------------------------------------


@given(parsers.parse('mitt konto är "{account}"'), target_fixture="ctx")
def account_ctx(account, bridge_pair, captured):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = bridge_pair[0]
    app.smtp = make_client(account)
    return ctx


@given(parsers.parse('att Bridge svarar NO på "{command}"'))
def bridge_refuses(bridge, command):
    bridge.refuse[command] = "operation failed"


@given(
    parsers.parse(
        'ett mejl i INBOX från "{sender}" med ämnet "{subject}" och bilagan "{filename}"'
    ),
    target_fixture="original",
)
def original_with_attachment(bridge, sender, subject, filename):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "me@proton.me"
    msg["Subject"] = subject
    msg["Date"] = "Mon, 12 Oct 2026 09:30:00 +0200"
    msg["Message-ID"] = "<orig-1@example.se>"
    msg.set_content("Originaltext")
    msg.add_attachment(PDF, maintype="application", subtype="pdf", filename=filename)
    return {"uid": bridge.add("INBOX", msg.as_bytes()), "msg": msg}


@given(parsers.parse('att SMTP-servern vägrar "{addr}"'))
def smtp_refuses(captured, addr):
    captured.refused[addr] = (550, "no such user")


# --- Then --------------------------------------------------------------------


@then(parsers.parse("ska Drafts innehålla {count:d} utkast"))
def drafts_count(bridge, count):
    assert len(bridge.messages("Drafts")) == count


@then(parsers.parse('utkastets text ska innehålla "{text}"'))
def draft_text(bridge, text):
    assert text in latest_draft(bridge).get_body(("plain",)).get_content()


@then(parsers.parse('ska anropet misslyckas med meddelandet "{text}"'))
def call_failed(outcome, text):
    assert "error" in outcome, f"inget fel: {outcome.get('result')!r}"
    assert text in str(outcome["error"])


@then("inget UID STORE eller UID EXPUNGE ska ha skickats")
def no_store_or_expunge(bridge):
    assert not {"UID STORE", "UID EXPUNGE", "EXPUNGE"} & set(bridge.names())


@then("inget mejl ska ha skickats")
def nothing_sent(captured):
    assert captured.sent == []

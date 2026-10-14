"""BDD-steg för utkastflödet (feat_utkast_*.feature).

Verktygen körs mot den riktiga IMAPClient och SMTPClient; bara aioimaplib
(låtsas-Bridge med riktiga meddelanden) och aiosmtplib är attrapper, så
stegen granskar både det som hamnar i Drafts och det som går ut på tråden.
"""
import asyncio
from unittest.mock import MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.drafts import create_draft
from tests.feat_utkast_bridge import make_imap
from tests.fix_svar_support import capture_smtp, header_addresses, make_client

scenarios("feat_utkast_skapa.feature")


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


def _run(outcome, coro):
    try:
        outcome["result"] = asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001 — scenariot granskar felet
        outcome["error"] = exc


def _latest_draft_uid(bridge) -> int:
    return max(bridge.messages("Drafts"))


# --- Given -------------------------------------------------------------------


@given(parsers.parse('mitt konto är "{account}"'), target_fixture="ctx")
def account_ctx(account, bridge_pair, captured):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = bridge_pair[0]
    app.smtp = make_client(account)
    return ctx


@given("att Bridge inte svarar med APPENDUID")
def no_appenduid(bridge):
    bridge.appenduid = False


@given(parsers.parse('att Bridge svarar NO på "{command}"'))
def bridge_refuses(bridge, command):
    bridge.refuse[command] = "operation failed"


# --- When --------------------------------------------------------------------


@when(
    parsers.parse(
        'jag skapar ett utkast till "{to}" med ämnet "{subject}" och texten "{body}"'
    )
)
def make_draft(ctx, outcome, to, subject, body):
    _run(outcome, create_draft(ctx, to=to, subject=subject, body=body))


@when(parsers.parse('jag skapar ett utkast till "{to}" med hemlig kopia till "{bcc}"'))
def make_draft_bcc(ctx, outcome, to, bcc):
    _run(outcome, create_draft(ctx, to=to, subject="Hej", body="Text", bcc=bcc))


# --- Then --------------------------------------------------------------------


@then(parsers.parse("ska Drafts innehålla {count:d} utkast"))
def drafts_count(bridge, count):
    assert len(bridge.messages("Drafts")) == count


@then(parsers.parse('utkastet ska ha flaggorna "{flags}"'))
def draft_flags(bridge, flags):
    msg = bridge.messages("Drafts")[_latest_draft_uid(bridge)]
    assert msg["flags"] == set(flags.split())


@then(
    parsers.re(
        r'utkastets header "(?P<name>[^"]+)" ska innehålla "(?P<display>[^"]*)" '
        r'med adressen "(?P<addr>[^"]+)"'
    )
)
def draft_header_contains(bridge, name, display, addr):
    msg = bridge.parsed("Drafts", _latest_draft_uid(bridge))
    assert (display, addr) in header_addresses(msg, name)


@then(parsers.parse('utkastets ämne ska vara "{subject}"'))
def draft_subject(bridge, subject):
    assert bridge.parsed("Drafts", _latest_draft_uid(bridge))["Subject"] == subject


@then(parsers.parse('utkastets text ska innehålla "{text}"'))
def draft_text(bridge, text):
    msg = bridge.parsed("Drafts", _latest_draft_uid(bridge))
    assert text in msg.get_body(("plain",)).get_content()


@then("inget mejl ska ha skickats")
def nothing_sent(captured):
    assert captured.sent == []


@then('svaret ska ange mappen "Drafts", utkastets UID och dess Message-ID')
def result_points_to_draft(bridge, outcome):
    assert "error" not in outcome, outcome.get("error")
    result = outcome["result"]
    uid = _latest_draft_uid(bridge)
    assert result["mailbox"] == "Drafts"
    assert result["uid"] == str(uid)
    assert result["message_id"] == bridge.parsed("Drafts", uid)["Message-ID"]


@then(parsers.parse('ska anropet misslyckas med meddelandet "{text}"'))
def call_failed(outcome, text):
    assert "error" in outcome, f"inget fel: {outcome.get('result')!r}"
    assert text in str(outcome["error"])

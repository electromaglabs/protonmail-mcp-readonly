"""BDD-steg för efterfix_skick_dolda_tecken.feature (gemensamma steg i conftest.py).

De dolda tecknen skrivs [U+E0041] osv. i feature-filen, så att de syns i
scenariot; stegen avkodar dem.
"""
import re
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.llm_skick_support import call_tool, make_app, record_smtp

from .conftest import _run, _settings

scenarios("efterfix_skick_dolda_tecken.feature")


def _decode(text: str) -> str:
    """[U+XXXX] i scenariot blir det (osynliga) tecknet med den kodpunkten."""
    return re.sub(r"\[U\+([0-9A-Fa-f]{4,6})\]", lambda m: chr(int(m.group(1), 16)), text)


def _raw(headers: dict[str, str]) -> bytes:
    lines = [f"{k}: {v}" for k, v in headers.items()]
    return ("\r\n".join(lines) + "\r\n\r\nHej\r\n").encode("utf-8")


@pytest.fixture(autouse=True)
def _appends(state):
    state["appends"] = []


def _call(state, tool, args):
    settings = _settings(state)
    app = make_app(settings, state["spy"])
    for setup in state["app_setup"]:
        setup(app)

    async def append(*a, **k):
        state["appends"].append(a)
        return "99"

    from protonmail_mcp import imap_drafts
    original = imap_drafts.append_draft
    imap_drafts.append_draft = append
    try:
        with record_smtp(state["spy"]) as captured:
            state["captured"] = captured
            _run(state, lambda: call_tool(tool, args, app, settings))
    finally:
        imap_drafts.append_draft = original


@given(parsers.parse('INBOX har ett mejl med UID "{uid}" med svarsadressen "{reply_to}"'))
def original_with_reply_to(state, uid, reply_to):
    raw = _raw({
        "From": "kund@exempel.se", "Reply-To": _decode(reply_to), "To": "me@proton.me",
        "Subject": "Fråga", "Message-ID": "<orig@exempel.se>",
    })
    state["app_setup"].append(lambda app: setattr(app.imap, "get_message", AsyncMock(return_value=raw)))


@given(parsers.parse('Drafts har ett utkast med UID "{uid}" till "{to}"'))
def draft_to(state, uid, to):
    raw = _raw({"From": "me@proton.me", "To": _decode(to), "Subject": "Hej", "Message-ID": "<d@proton.me>"})
    state["app_setup"].append(lambda app: setattr(app.imap, "get_message", AsyncMock(return_value=raw)))


@when(parsers.parse('LLM:en skickar ett mejl till adressen "{to}"'))
def llm_sends(state, to):
    _call(state, "send_email", {"to": _decode(to), "subject": "Hej", "body": "Hej"})


@when(parsers.parse('LLM:en svarar på UID "{uid}" i "{mailbox}"'))
def llm_replies(state, uid, mailbox):
    _call(state, "reply_to_email", {"uid": uid, "mailbox": mailbox, "body": "Tack"})


@when(parsers.parse('LLM:en skapar ett svarsutkast till UID "{uid}" i "{mailbox}"'))
def llm_reply_draft(state, uid, mailbox):
    _call(state, "create_reply_draft", {"uid": uid, "mailbox": mailbox, "body": "Tack"})


@when(parsers.parse('LLM:en vidarebefordrar UID "{uid}" i "{mailbox}" till adressen "{to}"'))
def llm_forwards(state, uid, mailbox, to):
    _call(state, "forward_email", {"uid": uid, "mailbox": mailbox, "to": _decode(to)})


@when(parsers.parse('LLM:en skickar utkastet med UID "{uid}"'))
def llm_sends_draft(state, uid):
    _call(state, "send_draft", {"uid": uid, "mailbox": "Drafts"})


@when(parsers.parse(
    'LLM:en skapar ett utkast till "{to}" med hemlig kopia till adressen "{bcc}"'
))
def llm_creates_draft(state, to, bcc):
    _call(state, "create_draft", {"to": to, "bcc": _decode(bcc), "subject": "Hej", "body": "Hej"})


@then("ska inget utkast ha sparats")
def no_draft(state):
    assert state["appends"] == []

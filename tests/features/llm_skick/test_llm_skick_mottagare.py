"""BDD-steg för llm_skick_mottagare.feature (gemensamma steg i conftest.py)."""
from email.message import EmailMessage
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.smtp_client import SMTPClient
from tests.llm_skick_support import call_tool, make_app, make_settings, record_smtp

from .conftest import _run, _settings

scenarios("llm_skick_mottagare.feature")


def _send_directly(state, **kwargs):
    smtp = SMTPClient(_settings(state))
    with record_smtp(state["spy"]) as captured:
        state["captured"] = captured
        _run(state, lambda: smtp.send_email(subject="Hej", body="Hej", **kwargs))


@when(parsers.parse('koden direkt i SMTP-klienten skickar ett mejl till "{to}" med kopia till "{cc}"'))
def send_with_cc(state, to, cc):
    _send_directly(state, to=to, cc=cc)


@when(parsers.parse('koden direkt i SMTP-klienten skickar ett mejl till "{to}" med hemlig kopia till "{bcc}"'))
def send_with_bcc(state, to, bcc):
    _send_directly(state, to=to, bcc=bcc)


def _message(uid_from: str, to: str, bcc: str | None = None, subject: str = "Hej") -> bytes:
    msg = EmailMessage()
    msg["From"] = uid_from
    msg["To"] = to
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = subject
    msg["Message-ID"] = "<original@exempel.se>"
    msg.set_content("Hej")
    return msg.as_bytes()


@given(parsers.parse('Drafts har utkastet med UID "{uid}" till "{to}" och hemlig kopia till "{bcc}"'))
def draft_in_drafts(state, uid, to, bcc):
    raw = _message("me@proton.me", to, bcc)

    def setup(app):
        app.imap.get_message = AsyncMock(return_value=raw)
    state["app_setup"].append(setup)


@given(parsers.parse('INBOX har ett mejl med UID "{uid}" från "{sender}"'))
def message_in_inbox(state, uid, sender):
    raw = _message(sender, "me@proton.me")

    def setup(app):
        app.imap.get_message = AsyncMock(return_value=raw)
    state["app_setup"].append(setup)


@when(parsers.parse('LLM:en vidarebefordrar UID "{uid}" i "{mailbox}" till "{to}"'))
def llm_forwards(state, uid, mailbox, to):
    settings = _settings(state)
    app = make_app(settings, state["spy"])
    for setup in state["app_setup"]:
        setup(app)
    with record_smtp(state["spy"]) as captured:
        state["captured"] = captured
        _run(state, lambda: call_tool("forward_email", {"uid": uid, "mailbox": mailbox, "to": to}, app, settings))


@then(parsers.parse('ska felet nämna "{text}"'))
def error_mentions(state, text):
    assert text in str(state["error"])


@then(parsers.parse('ska felet inte nämna "{address}" som otillåten'))
def error_does_not_list(state, address):
    assert address not in str(state["error"])


@when(parsers.parse('inställningen "{key}" läses som "{value}"'), target_fixture="validation")
def read_setting(key, value):
    with pytest.raises(ValidationError) as exc:
        make_settings(**{key: value})
    return exc.value


@then(parsers.parse('ska inställningen underkännas med ett fel som nämner "{text}"'))
def setting_rejected(validation, text):
    assert text in str(validation)

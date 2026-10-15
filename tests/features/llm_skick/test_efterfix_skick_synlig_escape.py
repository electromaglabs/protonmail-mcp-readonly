"""BDD-steg för efterfix_skick_synlig_escape.feature.

Stegen med "den kopierade adressen" använder adressen som den står, med
"[U+…]"-texten (det som en LLM kopierar ur visningen). Övriga steg (svarsadress
med råa dolda tecken, utkast, svar) kommer från test_efterfix_skick_dolda_tecken.
"""
from unittest.mock import AsyncMock

from pytest_bdd import given, parsers, scenarios, then, when

from . import test_efterfix_skick_dolda_tecken as dolda
from .test_efterfix_skick_dolda_tecken import _appends, _call, _raw  # noqa: F401 — _appends är en fixture

# Stegen från dolda tecken-scenarierna registreras även här (pytest-bdd
# knyter ett steg till modulen där dekoratorn körs)
given(parsers.parse('INBOX har ett mejl med UID "{uid}" med svarsadressen "{reply_to}"'))(
    dolda.original_with_reply_to
)
when(parsers.parse('LLM:en svarar på UID "{uid}" i "{mailbox}"'))(dolda.llm_replies)
when(parsers.parse('LLM:en skickar utkastet med UID "{uid}"'))(dolda.llm_sends_draft)
then("ska inget utkast ha sparats")(dolda.no_draft)

scenarios("efterfix_skick_synlig_escape.feature")


@given(parsers.parse('INBOX har ett vanligt mejl med UID "{uid}" från "{sender}"'))
def plain_original(state, uid, sender):
    raw = _raw({"From": sender, "To": "me@proton.me", "Subject": "Fråga", "Message-ID": "<o@exempel.se>"})
    state["app_setup"].append(lambda app: setattr(app.imap, "get_message", AsyncMock(return_value=raw)))


@given(parsers.parse('Drafts har ett utkast med UID "{uid}" till den kopierade adressen "{to}"'))
def draft_to_copied(state, uid, to):
    raw = _raw({"From": "me@proton.me", "To": to, "Subject": "Hej", "Message-ID": "<d@proton.me>"})
    state["app_setup"].append(lambda app: setattr(app.imap, "get_message", AsyncMock(return_value=raw)))


@when(parsers.parse('LLM:en skickar ett mejl till den kopierade adressen "{to}"'))
def send_copied(state, to):
    _call(state, "send_email", {"to": to, "subject": "Hej", "body": "Hej"})


@when(parsers.parse(
    'LLM:en svarar på UID "{uid}" i "{mailbox}" med kopia till den kopierade adressen "{cc}"'
))
def reply_with_copied_cc(state, uid, mailbox, cc):
    _call(state, "reply_to_email", {"uid": uid, "mailbox": mailbox, "body": "Tack", "cc": cc})


@when(parsers.parse('LLM:en skapar ett utkast till den kopierade adressen "{to}"'))
def draft_copied(state, to):
    _call(state, "create_draft", {"to": to, "subject": "Hej", "body": "Hej"})

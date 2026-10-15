"""BDD-steg för efterfix_skick_dubbletter.feature (gemensamma steg i conftest.py)."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.smtp_client import SMTPClient
from tests.llm_skick_support import record_smtp

from .conftest import _run, _settings

scenarios("efterfix_skick_dubbletter.feature")


def _send(state, **kwargs):
    smtp = SMTPClient(_settings(state))
    with record_smtp(state["spy"]) as captured:
        state["captured"] = captured
        _run(state, lambda: smtp.send_email(subject="Hej", body="Hej", **kwargs))


def _split(text):
    return [a.strip() for a in text.split(",")]


@when(parsers.parse(
    'koden direkt i SMTP-klienten skickar ett mejl till adresserna "{to}" med hemlig kopia till "{bcc}"'
))
def send_list_with_bcc(state, to, bcc):
    _send(state, to=_split(to), bcc=_split(bcc))


@when(parsers.parse('koden direkt i SMTP-klienten skickar ett mejl till adresserna "{to}"'))
def send_list(state, to):
    _send(state, to=_split(to))


@when(parsers.parse("koden direkt i SMTP-klienten skickar ett mejl till {count:d} adresser"))
def send_many(state, count):
    _send(state, to=[f"a{i}@exempel.se" for i in range(count)])

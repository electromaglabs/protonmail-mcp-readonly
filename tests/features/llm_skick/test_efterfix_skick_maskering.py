"""BDD-steg för efterfix_skick_maskering.feature (gemensamma steg i conftest.py)."""
import json
import logging

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.smtp_client import SMTPClient
from tests.llm_skick_support import record_smtp

from .conftest import _run, _settings

scenarios("efterfix_skick_maskering.feature")


@pytest.fixture(autouse=True)
def _audit_logs(caplog):
    caplog.set_level(logging.INFO, logger="protonmail_mcp.audit")


@given(parsers.parse("Bridge vägrar mottagaren '{address}'"))
def bridge_refuses(state, address):
    state["refuse"] = address


@when(parsers.parse(
    """koden direkt i SMTP-klienten skickar ett mejl till "{to}" med den hemliga kopian '{bcc}'"""
))
def send_with_secret_bcc(state, to, bcc):
    smtp = SMTPClient(_settings(state))
    with record_smtp(state["spy"]) as captured:
        if "refuse" in state:
            captured.refused[state["refuse"]] = (550, "no such user")
        state["captured"] = captured
        _run(state, lambda: smtp.send_email(to=to, bcc=bcc, subject="Hej", body="Hej"))


def _audit_line(caplog):
    lines = [r.getMessage() for r in caplog.records if r.name == "protonmail_mcp.audit"]
    assert lines, "ingen granskningsrad loggades"
    return lines[-1]


@then(parsers.parse('ska granskningsraden på stderr inte innehålla "{text}"'))
def stderr_lacks(caplog, text):
    assert text not in _audit_line(caplog)


@then(parsers.parse("ska granskningsraden på stderr nämna att {count:d} av mottagarna vägrades"))
def stderr_mentions_refused(caplog, count):
    entry = json.loads(_audit_line(caplog))
    assert entry["result"] == "error"
    assert f"vägrade {count}" in entry["error"]

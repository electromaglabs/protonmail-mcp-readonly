"""BDD-steg för llm_skick_granskning.feature (gemensamma steg i conftest.py)."""
import json
import logging
import os
import stat

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import imap_bulk
from protonmail_mcp.smtp_client import SMTPClient
from tests.llm_skick_support import call_tool, record_smtp, working_imap

from .conftest import _run, _settings

scenarios("llm_skick_granskning.feature")


@pytest.fixture(autouse=True)
def audit_records(caplog):
    caplog.set_level(logging.INFO, logger="protonmail_mcp.audit")
    return caplog


def _entries(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "protonmail_mcp.audit" and r.levelno == logging.INFO]


@given("granskningsloggen ska skrivas till en fil som inte finns än")
def audit_file(state, tmp_path):
    state["audit_path"] = tmp_path / "granskning.jsonl"
    state["overrides"]["audit_log"] = str(state["audit_path"])


@given("granskningsloggen ska skrivas till en symlänk som pekar på en annan fil")
def audit_symlink(state, tmp_path):
    target = tmp_path / "annan.txt"
    target.write_text("orörd\n")
    link = tmp_path / "granskning.jsonl"
    link.symlink_to(target)
    state["symlink_target"] = target
    state["overrides"]["audit_log"] = str(link)


@given(parsers.parse('Bridge har mejlen med UID "{uids}" i varje mapp'))
def bridge_has(state, uids):
    state["existing"] = set(uids.split(","))


@when(parsers.parse('koden skickar ett mejl till "{to}" med ämnet "{subject}" och texten "{body}"'))
def send(state, to, subject, body):
    smtp = SMTPClient(_settings(state))
    with record_smtp(state["spy"]) as captured:
        state["captured"] = captured
        _run(state, lambda: smtp.send_email(to=to, subject=subject, body=body))


@when(parsers.parse('LLM:en flyttar UID "{uid}" i "{mailbox}" till "{target}"'))
def llm_moves(state, uid, mailbox, target):
    from types import SimpleNamespace

    settings = _settings(state)
    app = SimpleNamespace(imap=working_imap(settings, state["existing"]), smtp=SMTPClient(settings))
    _run(state, lambda: call_tool("move_email", {"uid": uid, "mailbox": mailbox, "target_mailbox": target}, app, settings))


@when(parsers.parse('koden flyttar UID:na "{uids}" i "{mailbox}" till "{target}" med massflytt'))
def bulk_move(state, uids, mailbox, target):
    imap = working_imap(_settings(state), state["existing"])
    _run(state, lambda: imap_bulk.move(imap, mailbox, uids.split(","), target))


def _entry(caplog, action):
    found = [e for e in _entries(caplog) if e["action"] == action]
    assert found, f"ingen rad med action={action}: {_entries(caplog)}"
    return found[-1]


@then(parsers.parse('ska granskningsloggen ha en rad med åtgärden "{action}" och resultatet "{result}"'))
def has_entry(state, audit_records, action, result):
    entry = _entry(audit_records, action)
    assert entry["result"] == result
    assert "ts" in entry
    state["entry"] = entry


@then(parsers.parse('ska raden ha mottagarna "{addresses}" och mejlets Message-ID'))
def entry_recipients_and_id(state, addresses):
    assert state["entry"]["recipients"] == addresses.split(", ")
    assert state["entry"]["message_id"] == state["captured"].message["Message-ID"]


@then(parsers.parse('ska raden ha mottagarna "{addresses}"'))
def entry_recipients(state, addresses):
    assert state["entry"]["recipients"] == addresses.split(", ")


@then(parsers.parse('ska raden inte innehålla "{subject}", "{body}" eller lösenordet'))
def entry_has_no_content(state, audit_records, subject, body):
    text = "\n".join(r.getMessage() for r in audit_records.records)
    for secret in (subject, body, "pw"):
        assert secret not in json.dumps(state["entry"], ensure_ascii=False)
    assert subject not in text and body not in text


@then(parsers.parse('ska raden ha verktyget "{tool}", mappen "{mailbox}" och UID:na "{uids}"'))
def entry_tool_mailbox_uids(state, tool, mailbox, uids):
    entry = state["entry"]
    assert entry["tool"] == tool
    assert entry["mailbox"] == mailbox
    assert entry["uids"] == uids.split(",")


@then(parsers.parse('ska raden ange att UID "{ok}" lyckades och UID "{failed}" misslyckades'))
def entry_bulk(state, ok, failed):
    assert state["entry"]["ok_uids"] == [ok]
    assert state["entry"]["failed_uids"] == [failed]


@then(parsers.parse('ska raden ha verktyget "{tool}"'))
def entry_tool(state, tool):
    assert state["entry"]["tool"] == tool


@then("ska filen ha rättigheterna 0600")
def file_mode(state):
    assert stat.S_IMODE(os.stat(state["audit_path"]).st_mode) == 0o600


@then(parsers.parse('ska filen innehålla en JSON-rad med åtgärden "{action}"'))
def file_has_line(state, action):
    lines = state["audit_path"].read_text().splitlines()
    assert [json.loads(line)["action"] for line in lines] == [action]


@then("ska filen som symlänken pekar på vara orörd")
def symlink_target_untouched(state):
    assert state["symlink_target"].read_text() == "orörd\n"


@then("ska en varning om granskningsloggen ha loggats")
def warning_logged(audit_records):
    assert any(r.levelno == logging.WARNING and "granskningslogg" in r.getMessage() for r in audit_records.records)

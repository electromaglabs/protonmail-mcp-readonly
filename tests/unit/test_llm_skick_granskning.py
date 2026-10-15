"""Granskningsloggen (audit.py): fält, innehållsskydd och filskrivning."""
import json
import logging
import os
import stat
from email.message import EmailMessage

import pytest
from pydantic import ValidationError

from protonmail_mcp import audit, imap_bulk, imap_drafts, imap_labels
from tests.llm_skick_support import make_settings, working_imap


@pytest.fixture
def records(caplog):
    caplog.set_level(logging.INFO, logger="protonmail_mcp.audit")
    return caplog


def _entries(caplog) -> list[dict]:
    return [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "protonmail_mcp.audit" and r.levelno == logging.INFO
    ]


def test_record_has_fixed_and_given_fields(records):
    audit.record(make_settings(), "send", result="ok", recipients=["a@x.se"], message_id="<m@x>")
    (entry,) = _entries(records)
    assert entry["action"] == "send"
    assert entry["result"] == "ok"
    assert entry["tool"] is None
    assert entry["recipients"] == ["a@x.se"]
    assert entry["message_id"] == "<m@x>"
    assert entry["ts"].endswith("+00:00")


def test_record_skips_empty_fields(records):
    audit.record(make_settings(), "create_folder", result="ok", mailbox="Folders/A")
    (entry,) = _entries(records)
    assert set(entry) == {"ts", "tool", "action", "result", "mailbox"}


def test_error_text_is_truncated(records):
    audit.record(make_settings(), "send", result="error", error=ValueError("x" * 2000))
    (entry,) = _entries(records)
    assert entry["error"].startswith("ValueError: ")
    assert len(entry["error"]) <= 520


def test_tool_comes_from_context(records):
    token = audit.current_tool.set("move_email")
    try:
        audit.record(make_settings(), "move_message", result="ok")
    finally:
        audit.current_tool.reset(token)
    assert _entries(records)[0]["tool"] == "move_email"


def test_audit_logger_always_logs_info():
    assert audit.logger.getEffectiveLevel() <= logging.INFO


# --- Varje skrivfunktion loggas ------------------------------------------------

def _draft() -> bytes:
    msg = EmailMessage()
    msg["To"] = "anna@exempel.se"
    msg["Subject"] = "Hemligt ämne"
    msg.set_content("Hemlig text")
    return msg.as_bytes()


WRITES = {
    "set_flags": (lambda imap: imap.set_flags("INBOX", "5", r"(\Seen)", add=True), {"mailbox": "INBOX", "uids": ["5"]}),
    "move_message": (lambda imap: imap.move_message("INBOX", "5", "Archive"), {"mailbox": "INBOX", "target": "Archive"}),
    "delete_message": (lambda imap: imap.delete_message("Trash", "5", permanent=True), {"mailbox": "Trash", "permanent": True}),
    "create_folder": (lambda imap: imap.create_folder("Folders/Ny"), {"mailbox": "Folders/Ny"}),
    "rename_folder": (lambda imap: imap.rename_folder("Folders/Ny", "Folders/B"), {"mailbox": "Folders/Ny", "target": "Folders/B"}),
    "move": (lambda imap: imap_bulk.move(imap, "INBOX", ["5"], "Archive"), {"uids": ["5"], "ok_uids": ["5"]}),
    "delete": (lambda imap: imap_bulk.delete(imap, "INBOX", ["5"]), {"uids": ["5"]}),
    "set_starred": (lambda imap: imap_labels.set_starred(imap, "INBOX", ["5"], True), {"starred": True}),
    "append_draft": (lambda imap: imap_drafts.append_draft(imap, _draft(), "<d@x>"), {"mailbox": "Drafts", "message_id": "<d@x>"}),
}


@pytest.mark.parametrize("action", sorted(WRITES))
async def test_every_write_is_audited(records, monkeypatch, action):
    call, expected = WRITES[action]
    imap = working_imap(make_settings(), {"5"})
    imap._client.create.return_value = type("R", (), {"result": "OK", "lines": []})()
    imap._client.rename.return_value = type("R", (), {"result": "OK", "lines": []})()

    async def store(imap, message, message_id):
        return "12"

    monkeypatch.setattr(imap_drafts, "_store_draft", store)
    await call(imap)
    entries = [e for e in _entries(records) if e["action"] == action]
    assert len(entries) == 1, _entries(records)
    entry = entries[0]
    assert entry["result"] == "ok"
    for key, value in expected.items():
        assert entry[key] == value


async def test_draft_audit_has_no_content(records, monkeypatch):
    imap = working_imap(make_settings(), set())

    async def store(imap, message, message_id):
        return "12"

    monkeypatch.setattr(imap_drafts, "_store_draft", store)
    await imap_drafts.append_draft(imap, _draft(), "<d@x>")
    text = "\n".join(r.getMessage() for r in records.records)
    assert "Hemligt" not in text
    assert "Hemlig text" not in text
    assert _entries(records)[0]["new_uid"] == "12"


async def test_failed_write_is_audited_and_reraised(records):
    imap = working_imap(make_settings(), set())
    with pytest.raises(ValueError, match="Inget meddelande med UID 9"):
        await imap.move_message("INBOX", "9", "Archive")
    (entry,) = _entries(records)
    assert entry["result"] == "error"
    assert "UID 9" in entry["error"]


async def test_refused_write_is_audited(records):
    imap = working_imap(make_settings(read_only=True), set())
    with pytest.raises(ValueError, match="PROTONMAIL_READ_ONLY"):
        await imap.create_folder("Folders/Ny")
    (entry,) = _entries(records)
    assert entry == {**entry, "action": "create_folder", "result": "error", "mailbox": "Folders/Ny"}


# --- Filen -----------------------------------------------------------------------

def test_file_is_created_0600_and_appended(tmp_path, records):
    path = tmp_path / "audit.jsonl"
    settings = make_settings(audit_log=str(path))
    audit.record(settings, "send", result="ok")
    audit.record(settings, "move", result="ok")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert [json.loads(line)["action"] for line in path.read_text().splitlines()] == ["send", "move"]


def test_existing_file_is_tightened_to_0600(tmp_path, records):
    path = tmp_path / "audit.jsonl"
    path.write_text("")
    path.chmod(0o644)
    audit.record(make_settings(audit_log=str(path)), "send", result="ok")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_symlink_is_never_followed(tmp_path, records):
    target = tmp_path / "mål"
    target.write_text("orörd")
    link = tmp_path / "audit.jsonl"
    link.symlink_to(target)
    audit.record(make_settings(audit_log=str(link)), "send", result="ok")  # kastar inte
    assert target.read_text() == "orörd"
    assert any(r.levelno == logging.WARNING for r in records.records)


def test_hard_link_is_refused(tmp_path, records):
    other = tmp_path / "annan"
    other.write_text("orörd")
    path = tmp_path / "audit.jsonl"
    os.link(other, path)
    audit.record(make_settings(audit_log=str(path)), "send", result="ok")
    assert other.read_text() == "orörd"
    assert any(r.levelno == logging.WARNING for r in records.records)


def test_fifo_does_not_hang(tmp_path, records):
    path = tmp_path / "fifo"
    os.mkfifo(path)
    audit.record(make_settings(audit_log=str(path)), "send", result="ok")
    assert any(r.levelno == logging.WARNING for r in records.records)


def test_missing_directory_only_warns(tmp_path, records):
    audit.record(make_settings(audit_log=str(tmp_path / "saknas" / "audit.jsonl")), "send", result="ok")
    assert any(r.levelno == logging.WARNING for r in records.records)
    assert _entries(records)  # stderr-raden kommer ändå


def test_audit_log_defaults_to_none():
    assert make_settings().audit_log is None


def test_audit_log_must_be_absolute():
    with pytest.raises(ValidationError):
        make_settings(audit_log="relativ/audit.jsonl")


def test_audit_log_expands_home():
    settings = make_settings(audit_log="~/audit.jsonl")
    assert settings.audit_log.is_absolute()
    assert "~" not in str(settings.audit_log)

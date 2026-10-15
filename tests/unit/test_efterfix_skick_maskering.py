"""Maskeringen av adresser på stderr (audit.py): kända mottagare ersätts
först, citerade lokaldelar fångas och kapningen sker sist (granskning 3, policy F3)."""
import json
import logging
import time
from types import SimpleNamespace

import pytest

from protonmail_mcp import audit


def _stderr_entry(caplog, **kwargs):
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="protonmail_mcp.audit"):
        audit.record(SimpleNamespace(audit_log=None), "send", **kwargs)
    (line,) = [r.getMessage() for r in caplog.records if r.name == "protonmail_mcp.audit"]
    return line, json.loads(line)


@pytest.mark.parametrize(
    "address",
    ['"hemlig,bcc"@evil.com', '"x(y"@evil.com', '"a b"@evil.com', '"es\\"c"@evil.com'],
)
def test_quoted_local_part_is_masked_by_regex(caplog, address):
    # Adressen finns inte i recipients: regexet ensamt måste ta den
    line, _ = _stderr_entry(caplog, result="error", error=ValueError(f"Skicket vägrades: {address} finns inte"))
    assert "evil.com" not in line
    assert "<adress>" in line


def test_known_recipients_are_replaced_exactly(caplog):
    address = '"hemlig;x"@evil.com'
    line, _ = _stderr_entry(
        caplog, result="error", recipients=[address],
        error=ValueError(f"Skicket vägrades: {address} och {address.upper()} finns inte"),
    )
    assert "hemlig" not in line.lower() and "evil" not in line.lower()


def test_known_recipient_in_unicode_and_unquoted_form(caplog):
    line, _ = _stderr_entry(
        caplog, result="error", recipients=['"hemlig chef"@xn--exmple-cua.se'],
        error=ValueError("fel för hemlig chef@exämple.se och x@xn--exmple-cua.se"),
    )
    assert "hemlig" not in line and "exmple" not in line and "exämple" not in line


def test_masking_happens_before_clipping(caplog):
    # Kapningen vid 500 tecken hamnar mitt i den sista adressen: lokaldelen
    # får inte stå kvar omaskerad efter kapningen
    prefix = "x" * (audit._MAX_ERROR_CHARS - len("ValueError: ") - len("hemligt.namn@"))
    line, entry = _stderr_entry(caplog, result="error", error=ValueError(prefix + " hemligt.namn@firma.se"))
    assert "hemligt" not in line
    assert len(entry["error"]) <= audit._MAX_ERROR_CHARS + 2


def test_file_line_keeps_full_error(tmp_path):
    path = tmp_path / "audit.log"
    audit.record(SimpleNamespace(audit_log=path), "send", result="error",
                 recipients=['"hemlig,bcc"@evil.com'], error=ValueError('"hemlig,bcc"@evil.com vägrades'))
    entry = json.loads(path.read_text().strip())
    assert '"hemlig,bcc"@evil.com' in entry["error"]


def test_masking_is_linear_for_long_texts(caplog):
    text = "a" * 200_000 + " " + '"' * 50_000
    start = time.perf_counter()
    _stderr_entry(caplog, result="error", error=ValueError(text), recipients=["a@b.se"] * 1000)
    assert time.perf_counter() - start < 2


def test_many_known_recipients_are_masked_quickly():
    recipients = [f'"user{i}.hemlig"@exempel{i}.se' for i in range(1000)]
    text = "Skicket vägrades: " + ", ".join(recipients) + " finns inte"
    start = time.perf_counter()
    masked = audit.mask_addresses(text, recipients)
    assert time.perf_counter() - start < 2
    assert "hemlig" not in masked and "exempel" not in masked

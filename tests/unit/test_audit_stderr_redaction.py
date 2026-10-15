"""Granskningsraden på stderr (som t.ex. Claude Desktop sparar i en loggfil)
får inte innehålla mottagaradresser — inte minst Bcc. Fullständiga adresser
hamnar bara i den uttryckliga granskningsfilen PROTONMAIL_AUDIT_LOG."""
import json
import logging
from types import SimpleNamespace

from protonmail_mcp import audit


def _stderr_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "protonmail_mcp.audit"]


def test_stderr_line_has_recipient_count_not_addresses(caplog):
    with caplog.at_level(logging.INFO, logger="protonmail_mcp.audit"):
        audit.record(SimpleNamespace(audit_log=None), "send", result="ok",
                     recipients=["a@x.se", "hemlig@y.se"], message_id="<m@x>")
    (line,) = _stderr_lines(caplog)
    assert "a@x.se" not in line and "hemlig@y.se" not in line
    assert json.loads(line)["recipients"] == {"count": 2}


def test_stderr_error_text_masks_addresses(caplog):
    with caplog.at_level(logging.INFO, logger="protonmail_mcp.audit"):
        audit.record(SimpleNamespace(audit_log=None), "send", result="error",
                     error=ValueError("Mottagaren hemlig@y.se är inte tillåten"),
                     recipients=["hemlig@y.se"])
    (line,) = _stderr_lines(caplog)
    assert "hemlig@y.se" not in line


def test_audit_file_keeps_full_addresses(tmp_path):
    path = tmp_path / "audit.log"
    audit.record(SimpleNamespace(audit_log=path), "send", result="ok",
                 recipients=["a@x.se", "hemlig@y.se"])
    entry = json.loads(path.read_text().strip())
    assert entry["recipients"] == ["a@x.se", "hemlig@y.se"]

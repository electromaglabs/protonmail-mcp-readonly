"""Enhetstester för jämförelsen mellan dokumentation och kod (dokumentation)."""
from types import SimpleNamespace

import pytest

from tests import dokumentation_support as docs

SAMPLE = """\
# Titel

## Tools

Text som inte är en tabell, med `list_emails` i löptexten.

### Reading
| Tool | What it does | Effect |
|------|--------------|--------|
| `list_emails` | List emails | read-only |
| `send_email` | Send | **sends** |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PROTONMAIL_IMAP_PORT` | `1143` | IMAP port |
| `PROTONMAIL_USERNAME` | required | Address |
| `PROTONMAIL_AUDIT_LOG` | — | File |
| `PROTONMAIL_ALLOW_SEND` | — | Not in settings |
"""


def test_section_stops_at_next_heading_of_same_level():
    text = docs.section(SAMPLE, "Tools")
    assert "list_emails" in text
    assert "PROTONMAIL_IMAP_PORT" not in text


def test_missing_section_is_an_error():
    with pytest.raises(AssertionError, match="Prompts"):
        docs.section(SAMPLE, "Prompts")


def test_only_table_rows_with_code_in_first_cell_are_read():
    assert docs.documented_tools(SAMPLE) == {"list_emails": "read-only", "send_email": "sends"}


def test_duplicate_tool_rows_are_an_error():
    text = SAMPLE.replace("### Reading", "| `send_email` | again | sends |\n### Reading")
    with pytest.raises(AssertionError, match="send_email"):
        docs.documented_tools(text)


def test_settings_default_is_first_code_word_or_whole_cell():
    settings = docs.documented_settings(SAMPLE)
    assert settings["PROTONMAIL_IMAP_PORT"] == "1143"
    assert settings["PROTONMAIL_USERNAME"] == "required"
    assert settings["PROTONMAIL_AUDIT_LOG"] == "—"


@pytest.mark.parametrize(
    "hints, expected",
    [
        (dict(readOnlyHint=True, destructiveHint=False, openWorldHint=False), docs.READ_ONLY),
        (dict(readOnlyHint=False, destructiveHint=False, openWorldHint=False), docs.WRITES),
        (dict(readOnlyHint=False, destructiveHint=True, openWorldHint=False), docs.DESTRUCTIVE),
        (dict(readOnlyHint=False, destructiveHint=True, openWorldHint=True), docs.SENDS),
    ],
)
def test_effect_from_annotations(hints, expected):
    assert docs.effect(SimpleNamespace(**hints)) == expected


def test_expected_settings_cover_every_field_with_rendered_defaults():
    expected = docs.expected_settings()
    assert expected["PROTONMAIL_USERNAME"] == "required"
    assert expected["PROTONMAIL_IMAP_TIMEOUT"] == "30"
    assert expected["PROTONMAIL_READ_ONLY"] == "false"
    assert expected["PROTONMAIL_AUDIT_LOG"] == "—"
    assert expected["PROTONMAIL_ALLOWED_RECIPIENTS"] == "—"
    assert expected["PROTONMAIL_ATTACHMENT_DIR"] == "~/Downloads/protonmail-mcp"


def test_source_modules_include_tools_subpackage():
    modules = docs.source_modules()
    assert "server.py" in modules
    assert "tools/send.py" in modules
    assert not any("__pycache__" in m for m in modules)

"""Enhetstester: bevakningsinställningarna (ny-mejl)."""
import pytest
from pydantic import ValidationError

from protonmail_mcp.config import MAX_WATCH_MAILBOXES, Settings, parse_watch_mailboxes


def _settings(**kw):
    return Settings(username="u", password="p", _env_file=None, **kw)


def test_defaults():
    s = _settings()
    assert s.watch_enabled is True
    assert s.watch_mailboxes == "INBOX"
    assert s.watch_mailbox_list == ["INBOX"]


def test_max_is_five():
    assert MAX_WATCH_MAILBOXES == 5
    assert len(parse_watch_mailboxes("A,B,C,D,E")) == 5
    with pytest.raises(ValueError, match="högst 5"):
        parse_watch_mailboxes("A,B,C,D,E,F")


def test_inbox_is_case_insensitive_and_normalized():
    assert parse_watch_mailboxes("inbox, Inbox,INBOX") == ("INBOX",)


def test_other_names_keep_case_and_order():
    assert parse_watch_mailboxes("Folders/b, Folders/B") == ("Folders/b", "Folders/B")


def test_non_ascii_names_allowed():
    assert parse_watch_mailboxes("Labels/Näsa") == ("Labels/Näsa",)


@pytest.mark.parametrize("raw", ["INBOX,\x00", "Folders/A\nB", "x" * 256])
def test_invalid_names_rejected(raw):
    with pytest.raises(ValueError, match="Ogiltigt mappnamn"):
        parse_watch_mailboxes(raw)


def test_empty_list_rejected():
    with pytest.raises(ValueError, match="minst en mapp"):
        parse_watch_mailboxes(" , ,")


def test_settings_reject_invalid_list():
    with pytest.raises(ValidationError):
        _settings(watch_mailboxes="A,B,C,D,E,F")


def test_from_environment(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_WATCH_ENABLED", "0")
    monkeypatch.setenv("PROTONMAIL_WATCH_MAILBOXES", "INBOX,Folders/Kunder")
    s = _settings()
    assert s.watch_enabled is False
    assert s.watch_mailbox_list == ["INBOX", "Folders/Kunder"]

"""Enhetstester: valideringsfel i Settings visar inte indata (efterfix-verktyg, S4).

Utan hide_input_in_errors skriver pydantic input_value={'password': '...'}
i felet, och lifespan loggar felet till stderr.
"""
import pytest
from pydantic import ValidationError

from protonmail_mcp.config import Settings

SECRET = "HEMLIGT-bridge-losen"


def test_hide_input_in_errors_is_set():
    assert Settings.model_config.get("hide_input_in_errors") is True


def test_missing_username_error_does_not_contain_password(monkeypatch):
    monkeypatch.delenv("PROTONMAIL_USERNAME", raising=False)
    monkeypatch.setenv("PROTONMAIL_PASSWORD", SECRET)
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    assert "username" in str(excinfo.value)
    assert SECRET not in str(excinfo.value)
    assert SECRET not in repr(excinfo.value)


def test_invalid_timeout_error_does_not_contain_password(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user@proton.me")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", SECRET)
    monkeypatch.setenv("PROTONMAIL_IMAP_TIMEOUT", "0")
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    assert "imap_timeout" in str(excinfo.value)
    assert SECRET not in str(excinfo.value)

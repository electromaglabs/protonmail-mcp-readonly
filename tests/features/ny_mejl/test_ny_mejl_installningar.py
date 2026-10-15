"""BDD: PROTONMAIL_WATCH_ENABLED och PROTONMAIL_WATCH_MAILBOXES (ny-mejl)."""
import pytest
from pydantic import ValidationError
from pytest_bdd import given, parsers, scenarios, then

from protonmail_mcp.config import Settings

scenarios("ny_mejl_installningar.feature")


@pytest.fixture
def env(monkeypatch):
    for name in ("PROTONMAIL_WATCH_ENABLED", "PROTONMAIL_WATCH_MAILBOXES"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _settings():
    return Settings(username="u", password="p", _env_file=None)


@given("att inga bevakningsinställningar är satta")
def no_settings(env):
    pass


@given(parsers.parse('att {name} är "{value}"'))
def set_env(env, name, value):
    env.setenv(name, value.replace("\\r", "\r").replace("\\n", "\n"))


@then("ska bevakningen vara påslagen")
def enabled():
    assert _settings().watch_enabled is True


@then("ska bevakningen vara avstängd")
def disabled():
    assert _settings().watch_enabled is False


@then(parsers.parse('ska de bevakade mapparna vara "{names}"'))
def mailboxes(names):
    assert _settings().watch_mailbox_list == names.split("|")


@then(parsers.parse('ska inställningarna avvisas med "{text}"'))
def rejected(text):
    with pytest.raises(ValidationError, match=text.replace("(", r"\(")):
        _settings()

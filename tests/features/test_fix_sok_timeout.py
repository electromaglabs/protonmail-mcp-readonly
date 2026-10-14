"""BDD-tester: IMAP-timeouten är konfigurerbar (fix-sok, N8)."""
from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.config import Settings

scenarios("fix_sok_timeout.feature")


@given("att ingen IMAP-timeout är inställd")
def no_timeout(monkeypatch):
    monkeypatch.delenv("PROTONMAIL_IMAP_TIMEOUT", raising=False)


@given(parsers.parse('att PROTONMAIL_IMAP_TIMEOUT är "{value}"'))
def timeout_set(monkeypatch, value):
    monkeypatch.setenv("PROTONMAIL_IMAP_TIMEOUT", value)


@when("inställningarna läses", target_fixture="settings")
def read_settings(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    return Settings(_env_file=None)


@then(parsers.parse("ska IMAP-timeouten vara {seconds:d} sekunder"))
def timeout_is(settings, seconds):
    assert settings.imap_timeout == seconds


@when("IMAP-klienten skapas", target_fixture="client")
def create_client(monkeypatch):
    from protonmail_mcp.imap_client import IMAPClient
    return IMAPClient(read_settings(monkeypatch))


@then(parsers.parse("ska klientens kommandotimeout vara {seconds:d} sekunder"))
def client_timeout(client, seconds):
    assert client.timeout == seconds


@then(parsers.parse("ska klientens timeout för UID-kommandon vara {seconds:d} sekunder"))
def client_uid_timeout(client, seconds):
    assert client.uid_timeout == seconds

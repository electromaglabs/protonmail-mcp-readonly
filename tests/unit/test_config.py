"""Tests for config.py: Settings and get_settings()."""
import pytest
from pydantic import ValidationError

from protonmail_mcp.config import Settings, get_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("USERNAME", "PASSWORD", "IMAP_HOST", "IMAP_PORT", "ALLOWED_MAILBOXES"):
        monkeypatch.delenv(f"PROTONMAIL_{name}", raising=False)


class TestSettings:
    def test_loads_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "testuser")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "testpass")
        monkeypatch.setenv("PROTONMAIL_IMAP_HOST", "localhost")
        monkeypatch.setenv("PROTONMAIL_IMAP_PORT", "993")

        settings = Settings(_env_file=None)

        assert settings.username == "testuser"
        assert settings.password == "testpass"
        assert settings.imap_host == "localhost"
        assert settings.imap_port == 993

    def test_default_values(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")

        settings = Settings(_env_file=None)

        assert settings.imap_host == "127.0.0.1"
        assert settings.imap_port == 1143
        assert settings.allowed_mailboxes is None
        assert settings.allowed_mailbox_set is None

    def test_has_no_smtp_settings(self, monkeypatch):
        """This fork cannot send mail, so it has no SMTP configuration at all."""
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        # Leftover values from the original server are ignored, not an error
        monkeypatch.setenv("PROTONMAIL_SMTP_HOST", "127.0.0.1")
        monkeypatch.setenv("PROTONMAIL_SMTP_PORT", "1026")
        monkeypatch.setenv("PROTONMAIL_VERIFY_SSL", "false")

        settings = Settings(_env_file=None)

        assert not hasattr(settings, "smtp_host")
        assert not hasattr(settings, "smtp_port")

    def test_leftover_smtp_values_in_env_file_are_ignored(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "PROTONMAIL_USERNAME=user\n"
            "PROTONMAIL_PASSWORD=pass\n"
            "PROTONMAIL_SMTP_PORT=1026\n"
            "PROTONMAIL_VERIFY_SSL=false\n"
        )
        settings = Settings(_env_file=str(env_file))
        assert settings.username == "user"

    def test_validation_error_missing_username(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)

    def test_validation_error_missing_password(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)


class TestLoopbackOnly:
    """The IMAP connection is unencrypted, so only this computer is accepted."""

    @pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost", "LOCALHOST"])
    def test_accepts_loopback(self, monkeypatch, host):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        monkeypatch.setenv("PROTONMAIL_IMAP_HOST", host)
        assert Settings(_env_file=None).imap_host == host

    @pytest.mark.parametrize("host", ["10.0.0.1", "192.168.1.5", "mail.example.com", "0.0.0.0", ""])
    def test_rejects_other_hosts(self, monkeypatch, host):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        monkeypatch.setenv("PROTONMAIL_IMAP_HOST", host)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)


class TestAllowedMailboxes:
    def _settings(self, monkeypatch, value):
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        monkeypatch.setenv("PROTONMAIL_ALLOWED_MAILBOXES", value)
        return Settings(_env_file=None)

    def test_single_mailbox(self, monkeypatch):
        assert self._settings(monkeypatch, "Labels/Claude").allowed_mailbox_set == {"Labels/Claude"}

    def test_several_with_spaces(self, monkeypatch):
        s = self._settings(monkeypatch, " INBOX , Folders/My Stuff ,Labels/Claude")
        assert s.allowed_mailbox_set == {"INBOX", "Folders/My Stuff", "Labels/Claude"}

    @pytest.mark.parametrize("value", ["", "  ", ",", " , "])
    def test_empty_means_no_restriction(self, monkeypatch, value):
        assert self._settings(monkeypatch, value).allowed_mailbox_set is None


class TestGetSettings:
    def test_returns_settings_instance(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")

        assert isinstance(get_settings(), Settings)
        get_settings.cache_clear()

    def test_returns_cached_instance(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")

        assert get_settings() is get_settings()
        get_settings.cache_clear()

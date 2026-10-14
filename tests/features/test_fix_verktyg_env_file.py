"""BDD-tester: .env läses från projektroten oavsett CWD (fix-verktyg, punkt 15).

config.py kopieras till en temporär projektstruktur (<rot>/src/protonmail_mcp/)
så att testet aldrig läser eller skriver repots riktiga .env.
"""
import importlib.util
import shutil
from pathlib import Path

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

import protonmail_mcp.config as real_config

scenarios("fix_verktyg_env_file.feature")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ("PROTONMAIL_USERNAME", "PROTONMAIL_PASSWORD"):
        monkeypatch.delenv(key, raising=False)


@given(
    parsers.parse('en projektkatalog vars .env har användarnamnet "{username}"'),
    target_fixture="project_root",
)
def project_with_env(tmp_path, username):
    root = tmp_path / "projekt"
    pkg = root / "src" / "protonmail_mcp"
    pkg.mkdir(parents=True)
    shutil.copy(real_config.__file__, pkg / "config.py")
    (root / ".env").write_text(
        f"PROTONMAIL_USERNAME={username}\nPROTONMAIL_PASSWORD=hemligt\n"
    )
    return root


@given("att arbetskatalogen är en annan katalog utan .env")
def other_cwd(tmp_path, monkeypatch):
    cwd = tmp_path / "annanstans"
    cwd.mkdir()
    monkeypatch.chdir(cwd)


@given(parsers.parse('att arbetskatalogen har en .env med användarnamnet "{username}"'))
def cwd_with_env(tmp_path, monkeypatch, username):
    cwd = tmp_path / "annanstans"
    cwd.mkdir()
    (cwd / ".env").write_text(f"PROTONMAIL_USERNAME={username}\n")
    monkeypatch.chdir(cwd)


@when("inställningarna laddas", target_fixture="settings")
def load_settings(project_root):
    path = project_root / "src" / "protonmail_mcp" / "config.py"
    spec = importlib.util.spec_from_file_location("fix_verktyg_config_copy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Settings()


@then(parsers.parse('ska användarnamnet vara "{username}"'))
def username_is(settings, username):
    assert settings.username == username

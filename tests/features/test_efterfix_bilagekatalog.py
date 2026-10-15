"""BDD-steg för efterfix_bilagekatalog.feature (granskning 2, S1).

Allt byggs under tmp_path: en låtsas-hemkatalog med ~/.ssh och ~/Downloads.
"""
import asyncio
import logging
import os
from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import attachments as att
from protonmail_mcp.config import Settings, get_settings
from protonmail_mcp.server import lifespan, mcp

scenarios("efterfix_bilagekatalog.feature")

PRIVATE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n"
    "-----END OPENSSH PRIVATE KEY-----\n"
)


@pytest.fixture
def state():
    return {}


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("PROTONMAIL_USERNAME", "me@proton.me")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pw")
    monkeypatch.setenv("PROTONMAIL_ATTACHMENT_DIR", str(home / "Downloads" / "protonmail-mcp"))
    get_settings.cache_clear()
    yield home
    get_settings.cache_clear()


@pytest.fixture
def root(home):
    return home / "Downloads" / "protonmail-mcp"


def _files(directory: Path) -> set[Path]:
    return {p for p in directory.rglob("*") if p.is_file() and not p.is_symlink()}


@given(parsers.parse(
    'en hemkatalog med en privat nyckel i "{key}" och en hemlighet i "{secret}"'
))
def home_with_secrets(home, state, key, secret):
    (home / key).parent.mkdir(mode=0o700, parents=True)
    (home / key).write_text(PRIVATE_KEY)
    (home / secret).parent.mkdir(parents=True, exist_ok=True)
    (home / secret).write_text("PROTONMAIL_PASSWORD=hemligt\n")
    (home / "projekt" / "anteckning.txt").write_text("privat anteckning\n")


@given(parsers.parse('att bilagekatalogen är symlänken "{link}" som pekar på "{target}"'))
def root_is_symlink(home, state, link, target):
    (home / link).parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, home / link)
    state["files_before"] = _files(home)


@given(parsers.parse('att "{name}" är en symlänk till hemkatalogen'))
def ancestor_is_symlink(home, name):
    os.symlink(".", home / name)


@given(parsers.parse('att bilagekatalogen är "{rel}" med filen "{name}"'))
def root_with_file(home, root, rel, name):
    assert home / rel == root
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(b"%PDF-1.4 data")


@given("att bilagekatalogen har rättigheterna 777")
def root_world_writable(root):
    root.chmod(0o777)


@given("att bilagekatalogen ägs av en annan användare")
def root_foreign_owner(monkeypatch):
    other = os.getuid() + 1
    monkeypatch.setattr(att, "_current_uid", lambda: other, raising=False)


@given(parsers.parse(
    'en hård länk "{name}" i bilagekatalogen till "{target}" i hemkatalogen'
))
def hard_link(home, root, name, target):
    os.link(home / target, root / name)


@given(parsers.parse('att "{name}" i bilagekatalogen innehåller en privat OpenSSH-nyckel'))
def file_with_key(root, name):
    (root / name).write_text("Faktura 2026\n" + PRIVATE_KEY)


@given(parsers.parse('att PROTONMAIL_ATTACHMENT_DIR är "{value}"'))
def env_relative(home, monkeypatch, value):
    monkeypatch.setenv("PROTONMAIL_ATTACHMENT_DIR", value)


@given(parsers.parse('att PROTONMAIL_ATTACHMENT_DIR pekar på "{rel}" som inte finns'))
def env_missing(home, root, rel):
    assert home / rel == root
    assert not root.exists()


def _send(state, name):
    try:
        state["parts"] = att.load_for_sending([name])
    except ValueError as exc:
        state["error"] = exc


@when(parsers.parse('jag försöker skicka filen "{name}" som bilaga'))
def send_file(state, name):
    _send(state, name)


@when(parsers.parse('jag försöker skicka den absoluta sökvägen till "{rel}" som bilaga'))
def send_absolute(home, state, rel):
    _send(state, str(home / rel))


@when(parsers.parse('en bilaga sparas med filnamnet "{name}"'))
def save_file(state, name):
    try:
        state["saved"] = att.get_store().save(name, b"ssh-ed25519 AAAA angripare")
    except ValueError as exc:
        state["error"] = exc


@when("inställningarna läses in")
def read_settings(state):
    try:
        state["settings"] = Settings(_env_file=None)
    except ValidationError as exc:
        state["error"] = exc


@when("servern startar")
def start_server(state, caplog):
    async def run():
        async with lifespan(mcp):
            state["started"] = True

    caplog.set_level(logging.WARNING, logger="protonmail_mcp")
    asyncio.run(run())
    state["log"] = caplog.text


@then(parsers.parse('ska sändningen avvisas med ett fel som nämner "{text}"'))
def send_rejected(state, text):
    assert "parts" not in state, "bilagan byggdes"
    assert text in str(state["error"])


@then(parsers.parse('ska sparningen avvisas med ett fel som nämner "{text}"'))
def save_rejected(state, text):
    assert "saved" not in state, f"sparades som {state.get('saved')}"
    assert text in str(state["error"])


@then("ska ingen ny fil finnas i hemkatalogen")
def nothing_new(home, state):
    assert _files(home) == state["files_before"]


@then(parsers.parse('ska inläsningen misslyckas med ett fel som nämner "{text}"'))
def settings_rejected(state, text):
    assert "settings" not in state
    assert text in str(state["error"])


@then("ska bilagekatalogen finnas med rättigheterna 700")
def root_created(root):
    assert root.is_dir() and not root.is_symlink()
    assert (root.stat().st_mode & 0o777) == 0o700


@then("ska servern ha startat")
def server_started(state):
    assert state.get("started") is True


@then("ska loggen varna för bilagekatalogen")
def log_warns(state):
    assert "Bilagekatalogen" in state["log"]
    assert "symlänk" in state["log"]


@then(parsers.parse('ska symlänken "{link}" vara kvar'))
def symlink_kept(home, link):
    assert (home / link).is_symlink()


@then(parsers.parse('ska en bilaga med namnet "{name}" ha byggts'))
def part_built(state, name):
    assert "error" not in state, state.get("error")
    [part] = state["parts"]
    assert part.get_filename() == name

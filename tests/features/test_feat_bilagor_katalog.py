"""BDD-steg för feat_bilagor_katalog.feature (bilagekatalogens sökvägssäkerhet)."""
import os
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.attachments import AttachmentStore
from protonmail_mcp.config import Settings, get_settings
from tests.feat_bilagor_support import attachment_env, unescape  # noqa: F401

scenarios("feat_bilagor_katalog.feature")


@pytest.fixture
def state():
    return {}


@pytest.fixture
def root(attachment_env):
    return attachment_env[0]


@pytest.fixture
def outside(attachment_env):
    return attachment_env[1]


def _store(root: Path) -> AttachmentStore:
    return AttachmentStore(root)


@given("en bilagekatalog som inte finns ännu")
def missing_root(root):
    assert not root.exists()


@given("en tom bilagekatalog")
def empty_root(root):
    root.mkdir(mode=0o700)


@given(parsers.parse('en bilagekatalog som redan innehåller "{name}" med innehållet "{content}"'))
def root_with_file(root, name, content):
    root.mkdir(mode=0o700)
    (root / name).write_text(content)


@given(parsers.parse('filen "{name}" i bilagekatalogen'))
def file_in_root(root, name):
    (root / name).write_bytes(b"%PDF-1.4 offert")


@given(parsers.parse('underkatalogen "{name}" i bilagekatalogen'))
def dir_in_root(root, name):
    (root / name).mkdir()


@given(parsers.parse('en fil "{name}" utanför bilagekatalogen'))
def file_outside(outside, state, name):
    target = outside / name
    target.write_text("hemligt")
    state["outside_file"] = target


@given(parsers.parse('en symlänk "{name}" i bilagekatalogen som pekar på en fil utanför'))
def symlink_out(root, outside, state, name):
    target = outside / "mal.txt"
    target.write_text("orörd")
    state["outside_file"] = target
    (root / name).symlink_to(target)


@when(parsers.parse('en bilaga sparas med filnamnet "{name}"'))
def save_attachment(root, state, name):
    state["saved"] = _store(root).save(unescape(name), b"innehall")


@when(parsers.parse('en bilaga av typen "{ctype}" sparas med filnamnet "{name}"'))
def save_attachment_typed(root, state, ctype, name):
    state["saved"] = _store(root).save(unescape(name), b"innehall", content_type=ctype)


def _select(root, state, name):
    try:
        state["selected"] = _store(root).resolve_existing(name)
    except ValueError as exc:
        state["error"] = exc


@when(parsers.parse('jag väljer filen "{name}" att skicka'))
def select_file(root, state, name):
    _select(root, state, unescape(name))


@when(parsers.parse('jag väljer den absoluta sökvägen till "{name}" att skicka'))
def select_absolute(root, state, name):
    _select(root, state, str(root / name))


@when("jag väljer den absoluta sökvägen till filen utanför att skicka")
def select_absolute_outside(root, state):
    _select(root, state, str(state["outside_file"]))


@then("ska bilagekatalogen finnas med rättigheterna 700")
def root_mode(root):
    assert root.is_dir()
    assert (root.stat().st_mode & 0o777) == 0o700


@then(parsers.parse('ska filen "{name}" finnas i bilagekatalogen'))
def file_exists(root, state, name):
    assert (root / name).is_file()
    assert not (root / name).is_symlink()
    assert state["saved"] == (root / name).resolve()


@then("ska inget ha skrivits utanför bilagekatalogen")
def nothing_outside(root):
    parent = root.parent
    written = {p for p in parent.rglob("*") if p.is_file()}
    assert written == {p for p in root.rglob("*") if p.is_file()}


@then(parsers.parse('ska "{name}" fortfarande ha innehållet "{content}"'))
def unchanged(root, name, content):
    assert (root / name).read_text() == content


@then("ska filen utanför vara orörd")
def outside_untouched(state):
    assert state["outside_file"].read_text() == "orörd"


@then(parsers.parse('ska den valda filen vara "{name}" i bilagekatalogen'))
def selected_is(root, state, name):
    assert "error" not in state, state.get("error")
    assert state["selected"] == (root / name).resolve()


@then(parsers.parse('ska valet avvisas med ett fel som nämner "{text}"'))
def rejected(state, text):
    assert "selected" not in state
    assert text in str(state["error"])


@given("att PROTONMAIL_ATTACHMENT_DIR pekar på en egen katalog")
def env_dir(attachment_env):
    pass


@given("att PROTONMAIL_ATTACHMENT_DIR inte är satt")
def env_unset(attachment_env, monkeypatch):
    monkeypatch.delenv("PROTONMAIL_ATTACHMENT_DIR")


@when("inställningarna läses", target_fixture="settings")
def read_settings():
    get_settings.cache_clear()
    return Settings(_env_file=None)


@then("ska bilagekatalogen vara den katalogen")
def settings_dir(settings, root):
    assert settings.attachment_dir == root


@then(parsers.parse('ska bilagekatalogen vara "{path}" i hemkatalogen'))
def settings_default(settings, path):
    assert settings.attachment_dir == Path(os.path.expanduser(path))

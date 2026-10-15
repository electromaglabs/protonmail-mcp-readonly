"""BDD-steg för ci_linux_bilagekatalog.feature.

ext4 och overlayfs (GitHub Actions, Docker) återanvänder ofta inodnumret
direkt när en fil tas bort och en ny skapas, och i en container körs testerna
ofta som root. Båda simuleras här så att scenarierna beter sig likadant på
alla filsystem och för alla användare.
"""
import os
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import attachments as att

scenarios("ci_linux_bilagekatalog.feature")


@pytest.fixture
def state():
    return {}


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "bilagor"
    root.mkdir(mode=0o700)
    return root


@pytest.fixture
def store(root, state):
    """Bilagekatalogen som används — direkt, eller via en symlänk (steg nedan)."""
    return state.setdefault("store", att.AttachmentStore(root))


@pytest.fixture
def root_owned(monkeypatch):
    """Sökvägar vars lstat ska se ut att ägas av root (uid 0)."""
    paths: set[Path] = set()
    real_lstat = os.lstat

    def lstat(path, *a, **kw):
        st = real_lstat(path, *a, **kw)
        if Path(path) in paths:
            _, (seq, extra) = st.__reduce__()
            seq = list(seq)
            seq[4] = 0  # st_uid
            return os.stat_result(seq, extra)
        return st

    monkeypatch.setattr(att.os, "lstat", lstat)
    return paths


@given(parsers.parse('en bilagekatalog med filen "{name}"'))
def root_with_file(root, name):
    (root / name).write_bytes(b"%PDF-1.4 offert")


def _reuse_inode(checked, path):
    """Som ext4: den nya filen får samma (st_dev, st_ino) som den kontrollerade."""
    new = os.lstat(path)
    _, (seq, extra) = checked.stat.__reduce__()
    seq = list(seq)
    seq[1], seq[2] = new.st_ino, new.st_dev  # st_ino, st_dev
    return checked._replace(stat=os.stat_result(seq, extra))


@given(parsers.parse(
    'att "{name}" efter kontrollen byts mot en ny fil som återanvänder inodnumret'
))
def swapped_with_reused_inode(root, store, monkeypatch, name):
    checked = store._checked_file

    def swap(given_name):
        result = checked(given_name)
        (root / name).unlink()
        (root / name).write_bytes(b"helt annat innehall, och langre")
        return _reuse_inode(result, root / name)

    monkeypatch.setattr(store, "_checked_file", swap)


@given("att servern körs som root")
def running_as_root(monkeypatch):
    monkeypatch.setattr(att, "_current_uid", lambda: 0)


@given("att servern inte körs som root")
def not_running_as_root():
    if hasattr(os, "getuid") and os.getuid() == 0:
        pytest.skip("som root godtas inga symlänker på vägen till bilagekatalogen")


@given(parsers.parse('att bilagekatalogen nås via symlänken "{link}" som ägs av root'))
def root_via_root_owned_symlink(tmp_path, root, state, root_owned, link):
    assert "store" not in state
    path = tmp_path / link
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.symlink_to(tmp_path)
    root_owned.add(path)
    state["store"] = att.AttachmentStore(path / root.name)


@given(parsers.parse('att katalogen "{name}" har rättigheterna 777'))
def directory_world_writable(tmp_path, name):
    (tmp_path / name).chmod(0o777)


@when(parsers.parse('jag försöker skicka "{name}" som bilaga'))
def send(state, store, name):
    try:
        state["parts"] = att.load_for_sending([name], store)
    except ValueError as exc:
        state["error"] = exc


@then(parsers.parse('ska sändningen avvisas med ett fel som nämner "{text}"'))
def rejected(state, text):
    assert "parts" not in state, "bilagan byggdes"
    assert text in str(state["error"])


@then(parsers.parse('ska en bilaga med namnet "{name}" ha byggts'))
def built(state, name):
    assert "error" not in state, state.get("error")
    [part] = state["parts"]
    assert part.get_filename() == name

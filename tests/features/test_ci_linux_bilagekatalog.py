"""BDD-steg för ci_linux_bilagekatalog.feature.

ext4 och overlayfs (GitHub Actions, Docker) återanvänder ofta inodnumret
direkt när en fil tas bort och en ny skapas. Det simuleras här så att
scenariot beter sig likadant på alla filsystem.
"""
import os

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
def store(root):
    return att.AttachmentStore(root)


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

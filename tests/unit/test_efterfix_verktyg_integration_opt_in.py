"""Enhetstester: integrationstester körs bara med -m integration (efterfix-verktyg).

pytestmark i en conftest.py gäller inte testerna i katalogen, så markeringen
sätts av en collection-hook i tests/integration/conftest.py.
"""
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.integration import conftest as integration_conftest

ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_deselects_integration_by_default():
    opts = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]
    assert "-m 'not integration'" in opts["addopts"]


class _Item(SimpleNamespace):
    def __init__(self, path):
        super().__init__(path=path, markers=[])

    def add_marker(self, marker):
        self.markers.append(marker.mark if hasattr(marker, "mark") else marker)


def _names(item):
    return [m.name for m in item.markers]


def test_hook_marks_every_test_under_integration_dir(monkeypatch):
    monkeypatch.setattr(integration_conftest, "_env_available", lambda: True)
    inside = _Item(ROOT / "tests" / "integration" / "test_ny_fil_utan_pytestmark.py")
    outside = _Item(ROOT / "tests" / "unit" / "test_tools.py")
    integration_conftest.pytest_collection_modifyitems(None, [inside, outside])
    assert "integration" in _names(inside)
    assert "skip" not in _names(inside)
    assert outside.markers == []


def test_hook_skips_integration_without_config(monkeypatch):
    monkeypatch.setattr(integration_conftest, "_env_available", lambda: False)
    inside = _Item(ROOT / "tests" / "integration" / "test_imap.py")
    integration_conftest.pytest_collection_modifyitems(None, [inside])
    assert "skip" in _names(inside)


def test_env_vars_count_as_config(monkeypatch, tmp_path):
    monkeypatch.setattr(integration_conftest, "PROJECT_ROOT", tmp_path)  # ingen .env här
    monkeypatch.setenv("PROTONMAIL_USERNAME", "u@proton.me")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "x")
    assert integration_conftest._env_available() is True
    monkeypatch.delenv("PROTONMAIL_USERNAME")
    assert integration_conftest._env_available() is False

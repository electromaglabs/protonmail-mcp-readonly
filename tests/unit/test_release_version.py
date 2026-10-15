"""Enhetstester: versionen kommer från pyproject.toml (release)."""
from importlib.metadata import PackageNotFoundError

import pytest

from tests import release_support as rel


def test_package_version_is_pyproject_version():
    import protonmail_mcp

    assert protonmail_mcp.__version__ == rel.pyproject_version()


def test_server_reports_package_version_not_mcp_library_version():
    import protonmail_mcp
    from protonmail_mcp.server import mcp

    options = mcp._mcp_server.create_initialization_options()
    assert options.server_name == "protonmail"
    assert options.server_version == protonmail_mcp.__version__


def test_version_without_installed_metadata_is_marked_unknown(monkeypatch):
    """Körs koden utan installerat paket (ingen metadata) blir versionen
    tydligt okänd i stället för att servern inte startar."""
    import importlib

    import protonmail_mcp

    def missing(_name):
        raise PackageNotFoundError(_name)

    monkeypatch.setattr("importlib.metadata.version", missing)
    try:
        reloaded = importlib.reload(protonmail_mcp)
        assert reloaded.__version__ == "0+unknown"
    finally:
        monkeypatch.undo()
        importlib.reload(protonmail_mcp)
    assert protonmail_mcp.__version__ == rel.pyproject_version()

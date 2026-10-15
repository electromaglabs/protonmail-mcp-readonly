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


SAMPLE = """\
# Changelog

## [Unreleased]

## [0.3.0] - 2026-10-15

### Added
- Something

## [0.2.0] - 2026-03-16

[0.3.0]: https://example.com/compare/v0.2.0...v0.3.0
[0.2.0]: https://example.com/compare/v0.1.0...v0.2.0
"""


def test_changelog_sections_are_parsed_in_order():
    assert rel.changelog_sections(SAMPLE) == [
        ("Unreleased", None),
        ("0.3.0", "2026-10-15"),
        ("0.2.0", "2026-03-16"),
    ]


def test_changelog_links_are_parsed():
    assert rel.changelog_links(SAMPLE) == {
        "0.3.0": "https://example.com/compare/v0.2.0...v0.3.0",
        "0.2.0": "https://example.com/compare/v0.1.0...v0.2.0",
    }


@pytest.mark.parametrize(
    ("older", "newer"), [("0.2.0", "0.3.0"), ("0.9.0", "0.10.0"), ("0.3.0", "1.0.0")]
)
def test_version_key_orders_numerically(older, newer):
    assert rel.version_key(older) < rel.version_key(newer)


def test_changelog_starts_with_current_version():
    text = rel.CHANGELOG.read_text(encoding="utf-8")
    released = [v for v, _ in rel.changelog_sections(text) if v != "Unreleased"]
    assert released[0] == rel.pyproject_version()


def test_changelog_has_breaking_changes_first_in_current_section():
    """Uppgraderingsanteckningarna står först i den aktuella versionens avsnitt,
    före Added/Changed/Fixed, så att ingen missar dem."""
    text = rel.CHANGELOG.read_text(encoding="utf-8")
    current = text.split(f"## [{rel.pyproject_version()}]", 1)[1].split("\n## [", 1)[0]
    subsections = [line for line in current.splitlines() if line.startswith("### ")]
    assert subsections, "avsnittet har inga underrubriker"
    assert subsections[0].lower().startswith("### breaking changes")


def test_readme_links_changelog():
    assert "](CHANGELOG.md)" in rel.README.read_text(encoding="utf-8")

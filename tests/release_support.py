"""Hjälp för versionstesterna (release): pyproject.toml är versionens enda källa.

Paketet, serverns serverInfo och CHANGELOG.md ska ange samma version som
pyproject.toml, så att den som felsöker vet vilken version som körs och vad
som ändrats i den.
"""
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
README = ROOT / "README.md"

# Keep a Changelog: "## [0.3.0] - 2026-10-15" eller "## [Unreleased]"
_SECTION_RE = re.compile(r"^## \[(?P<version>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?\s*$", re.M)
# Länkdefinitionerna längst ned: "[0.3.0]: https://…"
_LINK_RE = re.compile(r"^\[(?P<version>[^\]]+)\]: (?P<url>\S+)\s*$", re.M)


def pyproject_version() -> str:
    """Versionen i pyproject.toml (projektets enda versionskälla)."""
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def changelog_sections(text: str) -> list[tuple[str, str | None]]:
    """(version, datum) för varje versionsavsnitt, i den ordning de står."""
    return [(m["version"], m["date"]) for m in _SECTION_RE.finditer(text)]


def changelog_links(text: str) -> dict[str, str]:
    """Version → URL ur länkdefinitionerna."""
    return {m["version"]: m["url"] for m in _LINK_RE.finditer(text)}


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


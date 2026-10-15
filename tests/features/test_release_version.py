"""BDD: versionen anges i pyproject.toml och stämmer överallt (release)."""
import asyncio
from importlib.metadata import version as package_version

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests import release_support as rel
from tests.llm_kontrakt_support import client_session

scenarios("release_version.feature")


@pytest.fixture
def context():
    return {}


@given("versionen i pyproject.toml")
def pyproject(context):
    context["version"] = rel.pyproject_version()


@given("CHANGELOG.md")
def changelog(context):
    context["changelog"] = rel.CHANGELOG.read_text(encoding="utf-8")


@given("README.md")
def readme(context):
    context["readme"] = rel.README.read_text(encoding="utf-8")


@when("en MCP-klient ansluter till servern")
def connect(context, monkeypatch):
    async def run():
        async with rel.capture_initialize(monkeypatch) as captured:
            async with client_session(monkeypatch):
                pass
        return captured["result"]

    context["init"] = asyncio.run(run())


@then(parsers.parse('ska serverInfo ha namnet "{name}"'))
def server_name(context, name):
    assert context["init"].serverInfo.name == name


@then("ska serverInfo ha versionen ur pyproject.toml, inte MCP-bibliotekets")
def server_version(context):
    reported = context["init"].serverInfo.version
    assert reported == context["version"], (
        f"serverInfo.version är {reported!r} (mcp-biblioteket är {package_version('mcp')!r}), "
        f"pyproject.toml säger {context['version']!r}"
    )


@then("ska protonmail_mcp.__version__ vara versionen ur pyproject.toml")
def package_dunder_version(context):
    import protonmail_mcp

    assert protonmail_mcp.__version__ == context["version"]


@then("ska det senaste versionsavsnittet i CHANGELOG.md vara versionen ur pyproject.toml")
def latest_section(context):
    released = [v for v, _ in rel.changelog_sections(context["changelog"]) if v != "Unreleased"]
    assert released, "CHANGELOG.md har inga versionsavsnitt"
    assert released[0] == context["version"]


@then("ska varje versionsavsnitt ha ett datum och en länk")
def dated_and_linked(context):
    links = rel.changelog_links(context["changelog"])
    for version, date in rel.changelog_sections(context["changelog"]):
        if version == "Unreleased":
            continue
        assert date, f"## [{version}] saknar datum"
        assert version in links, f"[{version}] saknar länkdefinition längst ned"


@then("ska versionsavsnitten stå med den nyaste först")
def newest_first(context):
    released = [v for v, _ in rel.changelog_sections(context["changelog"]) if v != "Unreleased"]
    assert released == sorted(released, key=rel.version_key, reverse=True)


@then("ska README.md länka till CHANGELOG.md")
def readme_links_changelog(context):
    assert "](CHANGELOG.md)" in context["readme"]

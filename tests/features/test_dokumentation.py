"""BDD: README.md och CLAUDE.md följer koden (dokumentation)."""
import asyncio

import pytest
from pytest_bdd import given, scenarios, then

from tests import dokumentation_support as docs

scenarios("dokumentation.feature")


@pytest.fixture
def context():
    return {}


@given("README.md och den registrerade servern")
def readme_and_server(context):
    context["readme"] = docs.README.read_text(encoding="utf-8")
    context["tools"] = asyncio.run(docs.registered_tools())
    context["resources"] = asyncio.run(docs.registered_resources())
    context["prompts"] = asyncio.run(docs.registered_prompts())


@given("CLAUDE.md och källkoden")
def claude_md_and_source(context):
    context["claude_md"] = docs.CLAUDE_MD.read_text(encoding="utf-8")


def _diff(documented, actual) -> str:
    return (
        f"saknas i dokumentationen: {sorted(set(actual) - set(documented))}, "
        f"finns inte i koden: {sorted(set(documented) - set(actual))}"
    )


@then("ska verktygstabellerna i README.md innehålla exakt serverns verktyg")
def tools_match(context):
    documented = docs.documented_tools(context["readme"])
    assert set(documented) == set(context["tools"]), _diff(documented, context["tools"])


@then("ska effektkolumnen för varje verktyg stämma med verktygets annoteringar")
def effects_match(context):
    documented = docs.documented_tools(context["readme"])
    wrong = {
        name: (documented[name], expected)
        for name, expected in context["tools"].items()
        if name in documented and documented[name] != expected
    }
    assert not wrong, f"fel effekt (README, annoteringar): {wrong}"


@then("ska inställningstabellen i README.md innehålla exakt inställningarna i config.py")
def settings_match(context):
    documented = docs.documented_settings(context["readme"])
    expected = docs.expected_settings()
    assert set(documented) == set(expected), _diff(documented, expected)


@then("ska varje inställnings standardvärde stämma med config.py")
def defaults_match(context):
    documented = docs.documented_settings(context["readme"])
    wrong = {
        name: (documented[name], default)
        for name, default in docs.expected_settings().items()
        if name in documented and documented[name] != default
    }
    assert not wrong, f"fel standardvärde (README, config.py): {wrong}"


@then("ska resurstabellen i README.md innehålla exakt serverns resurser och resursmallar")
def resources_match(context):
    documented = docs.documented_names(context["readme"], docs.RESOURCES_SECTION)
    assert documented == context["resources"], _diff(documented, context["resources"])


@then("ska prompttabellen i README.md innehålla exakt serverns promptar")
def prompts_match(context):
    documented = docs.documented_names(context["readme"], docs.PROMPTS_SECTION)
    assert documented == context["prompts"], _diff(documented, context["prompts"])


@then("ska modulkartan i CLAUDE.md innehålla exakt modulerna i src/protonmail_mcp")
def modules_match(context):
    documented = docs.documented_modules(context["claude_md"])
    actual = docs.source_modules()
    assert documented == actual, _diff(documented, actual)

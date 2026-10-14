"""BDD: list_mailboxes returnerar typ, valbarhet och special-use från LIST-attributen."""
from pytest_bdd import parsers, then
from pytest_bdd import scenarios

scenarios("fix_mappnamn_attribut.feature")


def _mapp(mappar, name):
    matches = [m for m in mappar if m["name"] == name]
    assert len(matches) == 1, [m["name"] for m in mappar]
    return matches[0]


@then(parsers.parse('ska mappen "{name}" vara av typen "{typ}"'))
def has_type(mappar, name, typ):
    assert _mapp(mappar, name)["type"] == typ


@then(parsers.parse('ska mappen "{name}" ha special-use "{special_use}"'))
def has_special_use(mappar, name, special_use):
    assert _mapp(mappar, name)["special_use"] == special_use


@then(parsers.parse('ska mappen "{name}" sakna special-use'))
def has_no_special_use(mappar, name):
    assert _mapp(mappar, name)["special_use"] is None


@then(parsers.parse('ska mappen "{name}" inte gå att välja'))
def not_selectable(mappar, name):
    assert _mapp(mappar, name)["selectable"] is False


@then("ska alla dessa mappar gå att välja")
def all_selectable(mappar):
    assert [m["selectable"] for m in mappar] == [True] * len(mappar)

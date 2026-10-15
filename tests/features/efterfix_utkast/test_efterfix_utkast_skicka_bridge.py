"""BDD-steg för efterfix_utkast_skicka_bridge.feature (send_draft och Bridges egen borttagning)."""
from types import SimpleNamespace

from pytest_bdd import given, parsers, scenarios, then

scenarios("efterfix_utkast_skicka_bridge.feature")


@given("att Bridge tar bort utkastet ur Drafts när det skickas")
def bridge_deletes_on_send(bridge, captured, draft):
    captured.after_send.append(lambda _msg: bridge.messages("Drafts").pop(int(draft["uid"])))


@given("att Bridge tar bort utkastet och svarar NO när send_draft raderar det")
def bridge_deletes_during_expunge(bridge, draft):
    inner = bridge.client.uid.side_effect

    async def uid(command, *args):
        if command.upper() == "EXPUNGE":
            bridge.commands.append(("UID EXPUNGE", *args))
            bridge.messages("Drafts").pop(int(draft["uid"]), None)
            return SimpleNamespace(result="NO", lines=[b"message not found"])
        return await inner(command, *args)

    bridge.client.uid.side_effect = uid


@then(parsers.parse('SMTP-mottagarna ska vara "{recipients}"'))
def smtp_recipients(captured, recipients):
    assert captured.recipients == [r.strip() for r in recipients.split(",")]


@then("svaret ska ange att utkastet togs bort utan varning")
def deleted_without_warning(outcome):
    assert "error" not in outcome, outcome.get("error")
    result = outcome["result"]
    assert result["sent"] is True
    assert result["draft_deleted"] is True
    assert "warning" not in result


@then("svaret ska förklara att Bridge tar bort utkastet själv")
def explains_bridge_deletes(outcome):
    assert "Bridge" in outcome["result"]["note"]


@then(parsers.parse('det skickade mejlet ska sakna rubriker som börjar med "{prefix}"'))
def sent_lacks_prefix(captured, prefix):
    assert not [k for k in captured.parsed.keys() if k.lower().startswith(prefix.lower())]
    assert prefix.lower().encode() not in captured.raw.lower()


@then(parsers.parse('det skickade mejlets "{name}" ska innehålla "{value}"'))
def sent_header_contains(captured, name, value):
    assert value in (captured.parsed[name] or "")

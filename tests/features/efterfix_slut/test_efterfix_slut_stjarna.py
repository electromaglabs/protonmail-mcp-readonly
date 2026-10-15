"""BDD: unflag_email tar inte bort stjärnan från en tvilling (G5K-3)."""
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.labels import unflag_email

from .conftest import run_tool

scenarios("efterfix_slut_stjarna.feature")


@given(parsers.parse(
    'att ett annat mejl "{name}" med samma Message-ID "{mid}", tid och storlek är stjärnmärkt '
    'i "{mailbox}" med UID "{uid}" och i Starred med UID "{suid}"'
))
def starred_twin(bridge, name, mid, mailbox, uid, suid):
    key = bridge.put_twin(mailbox, uid, mid, flags=("\\Flagged",))
    bridge.put("Starred", suid, key)
    bridge.twins[name] = key


@given(parsers.parse('att mejlet "{mid}" är stjärnmärkt med UID "{uid}" i "{mailbox}" och UID "{suid}" i Starred'))
def starred_mail(bridge, mid, uid, mailbox, suid):
    bridge.put_mail(mailbox, uid, mid, flags=("\\Flagged",))
    bridge.put("Starred", suid, mid)


@when(parsers.parse('jag tar bort stjärnmärkningen på UID "{uid}" i "{mailbox}"'))
def unflag(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, unflag_email(mock_ctx, uid=uid, mailbox=mailbox))


@then(parsers.parse('ska mejlet "{name}" vara stjärnmärkt'))
def flagged(bridge, name):
    assert "\\Flagged" in bridge.messages[bridge.twins.get(name, name)]["flags"]


@then(parsers.parse('ska mejlet "{name}" inte vara stjärnmärkt'))
def not_flagged(bridge, name):
    assert "\\Flagged" not in bridge.messages[bridge.twins.get(name, name)]["flags"]

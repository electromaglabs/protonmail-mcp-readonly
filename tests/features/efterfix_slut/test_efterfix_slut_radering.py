"""BDD: Code=2501 vid permanent radering — kontroll i All Mail för alla mejl i omgången (G5K-1)."""
from pytest_bdd import given, parsers, scenarios, when

from protonmail_mcp.tools.manage import delete_email

from .conftest import run_tool, uid_list

scenarios("efterfix_slut_radering.feature")


@given(parsers.parse('att mejlet "{mid}" redan är raderat i Proton men fortfarande syns i Bridge'))
def phantom(bridge, mid):
    bridge.phantoms.add(mid)


@given(parsers.parse(
    'att Bridge svarar NO med Code=2501 på permanent radering i "{mailbox}" och avbryter omgången'
))
def no_then_vanish(bridge, mailbox):
    bridge.no_then_vanish[mailbox] = [1, 1]


@given("att Bridge nekar sökningar")
def refuse_search(bridge):
    bridge.refuse["SEARCH"] = "SEARCH nekad"


@when(parsers.parse('jag raderar UID-listan "{uids}" i "{mailbox}" permanent'))
def delete_list(mock_ctx, bridge, uids, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid_list(uids), mailbox=mailbox, permanent=True))


@when(parsers.parse('jag raderar mejlet med UID "{uid}" i "{mailbox}" permanent'))
def delete_one(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid, mailbox=mailbox, permanent=True))

"""BDD: bästa försök-steg fångar timeout och avbrott och redovisar dem (G5K-5)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.labels import unflag_email
from protonmail_mcp.tools.manage import delete_email

from .conftest import run_tool, uid_list

scenarios("efterfix_slut_basta_forsok.feature")


@given(parsers.parse('att mejlet "{mid}" är stjärnmärkt med UID "{uid}" i "{mailbox}" och UID "{suid}" i Starred'))
def starred_mail(bridge, mid, uid, mailbox, suid):
    bridge.put_mail(mailbox, uid, mid, flags=("\\Flagged",))
    bridge.put("Starred", suid, mid)


@given(parsers.parse('att Bridge inte svarar på sökningar i "{view}"'))
def search_hangs(bridge, view):
    real = bridge.client.search.side_effect

    async def search(*args, **kwargs):
        if bridge.selected == view:
            raise asyncio.TimeoutError()
        return await real(*args, **kwargs)

    bridge.client.search.side_effect = search


@given(parsers.parse(
    'att Bridge svarar NO med Code=2501 på permanent radering i "{mailbox}" och avbryter omgången'
))
def no_then_vanish(bridge, mailbox):
    bridge.no_then_vanish[mailbox] = [1, 1]


@when(parsers.parse('jag tar bort stjärnmärkningen på UID "{uid}" i "{mailbox}"'))
def unflag(mock_ctx, bridge, uid, mailbox):
    run_tool(bridge, unflag_email(mock_ctx, uid=uid, mailbox=mailbox))


@when(parsers.parse('jag raderar UID-listan "{uids}" i "{mailbox}" permanent'))
def delete_list(mock_ctx, bridge, uids, mailbox):
    run_tool(bridge, delete_email(mock_ctx, uid=uid_list(uids), mailbox=mailbox, permanent=True))


@then(parsers.parse('ska mejlet "{mid}" inte vara stjärnmärkt'))
def not_flagged(bridge, mid):
    assert "\\Flagged" not in bridge.messages[mid]["flags"]

"""BDD: väntan efter Code=2501 håller inte IMAP-låset (G5K-4)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import imap_client
from protonmail_mcp.tools.manage import delete_email, mark_email_read

from .conftest import uid_list

scenarios("efterfix_slut_las.feature")


@given(parsers.parse(
    'att Bridge svarar NO med Code=2501 på permanent radering i "{mailbox}" och mejlen blir kvar'
))
def no_and_stays(bridge, mailbox, monkeypatch):
    monkeypatch.setattr(imap_client, "_GONE_TIMEOUT", 1.0)
    monkeypatch.setattr(imap_client, "_GONE_INTERVAL", 0.05)
    bridge.no_then_vanish[mailbox] = [10**9, 1]


@when(parsers.parse(
    'jag raderar UID-listan "{uids}" i "{mailbox}" permanent och samtidigt markerar UID "{uid}" i "{other}" som läst'
))
def delete_and_mark(mock_ctx, bridge, uids, mailbox, uid, other):
    async def both():
        delete = asyncio.create_task(
            delete_email(mock_ctx, uid=uid_list(uids), mailbox=mailbox, permanent=True)
        )
        while not bridge.sent("UID EXPUNGE"):
            await asyncio.sleep(0.005)
        await mark_email_read(mock_ctx, uid=uid, mailbox=other)
        bridge.mark_done_while_waiting = not delete.done()
        return await delete

    bridge.result = asyncio.run(both())


@then("ska markeringen ha svarat medan raderingen fortfarande väntade")
def marked_while_waiting(bridge):
    assert bridge.mark_done_while_waiting
    assert "\\Seen" in bridge.messages["<b@x>"]["flags"]

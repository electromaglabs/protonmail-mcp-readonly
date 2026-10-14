"""BDD: search_emails hämtar TO och MESSAGE-ID som list_emails (K7)."""
from pytest_bdd import given, parsers, scenarios, then

from .conftest import install_bodies

scenarios("efterfix_imap_sok_to_message_id.feature")


@given(parsers.parse('att mejlet med UID "{uid}" i "{mailbox}" är skickat till "{to}" med Message-ID "{mid}"'))
def mail_with_to(bridge, uid, mailbox, to, mid):
    install_bodies(bridge)
    bridge.add(mailbox, uid)
    bridge.bodies[(mailbox, uid)] = (
        f"Subject: Hej\r\nFrom: x@example.com\r\nTo: {to}\r\nMessage-ID: {mid}\r\n"
        "Date: Mon, 5 Oct 2026 10:00:00 +0200\r\n\r\n"
    ).encode()


@then(parsers.parse('ska träffen med UID "{uid}" ha to "{to}" och message_id "{mid}"'))
def hit_has(bridge, uid, to, mid):
    assert bridge.errors == []
    hit = next(m for m in bridge.result["messages"] if m["uid"] == uid)
    assert (hit["to"], hit["message_id"]) == (to, mid)

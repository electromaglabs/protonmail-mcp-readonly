"""BDD: STATUS-svarets antal tolkas bara ur parentesen, inte ur mappnamnet (K1/F1)."""
from pytest_bdd import parsers, scenarios, then

scenarios("efterfix_imap_status_namn.feature")


@then(parsers.parse("ska statusen vara {messages:d} mejl och {unseen:d} olästa"))
def status_is(bridge, messages, unseen):
    assert bridge.errors == []
    assert bridge.result == {"messages": messages, "unseen": unseen}

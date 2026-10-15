"""BDD (efterfix-tradetikett): etikettverktygen svarar rätt per UID i svåra fall."""
from pytest_bdd import given, parsers, scenarios, when

from protonmail_mcp.tools.labels import remove_label

from .conftest import run_tool, uid_list

scenarios("efterfix_tradetikett_etiketter.feature")


@given(parsers.parse(
    'att Bridge tar bort etiketten från UID "{done}" men sedan nekar UID EXPUNGE med "{text}"'
))
def partial_expunge(bridge, done, text):
    original = bridge.client.uid.side_effect

    async def uid(command, *args):
        if command.upper() == "EXPUNGE":
            bridge.commands.append(("UID EXPUNGE", *args))
            if (bridge.selected, done) in bridge.deleted:
                bridge._detach(bridge.selected, done)
            from tests.feat_etiketter_bridge import _no

            return _no(text)
        return await original(command, *args)

    bridge.client.uid.side_effect = uid


@when(parsers.parse('jag tar bort etiketten "{label}" från UID-listan "{uids}" i "{mailbox}"'))
def remove_label_list(mock_ctx, bridge, label, uids, mailbox):
    run_tool(bridge, remove_label(mock_ctx, uid=uid_list(uids), mailbox=mailbox, label=label))

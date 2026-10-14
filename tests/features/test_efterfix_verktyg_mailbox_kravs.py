"""BDD: skrivverktygen kräver mailbox, eftersom UID gäller per mapp (efterfix-verktyg, F2)."""
import asyncio

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.server import mcp
from protonmail_mcp.tools import manage, messages, search  # noqa: F401  registrerar verktygen

scenarios("efterfix_verktyg_mailbox_kravs.feature")

_IMAP_CALL = {
    "delete_email": "delete_message",
    "move_email": "move_message",
    "mark_email_read": "set_flags",
    "mark_email_unread": "set_flags",
}


def _imap(mock_ctx):
    return mock_ctx.request_context.lifespan_context.imap


def _tool(name):
    return mcp._tool_manager.get_tool(name)


def _args(verktyg, uid, mailbox=None):
    args = {"uid": uid}
    if verktyg == "move_email":
        args["target_mailbox"] = "Archive"
    if mailbox is not None:
        args["mailbox"] = mailbox
    return args


@given(parsers.parse('att INBOX har ett annat brev med UID "{uid}"'))
def inbox_has_other(mock_ctx, uid):
    imap = _imap(mock_ctx)
    for call in set(_IMAP_CALL.values()):
        getattr(imap, call).return_value = True


@when(parsers.parse('jag anropar {verktyg} med uid "{uid}" utan mapp'), target_fixture="outcome")
def call_without_mailbox(mock_ctx, verktyg, uid):
    try:
        return {"result": asyncio.run(_tool(verktyg).run(_args(verktyg, uid), context=mock_ctx))}
    except Exception as exc:  # noqa: BLE001 — scenariot granskar felet
        return {"error": exc}


@when(
    parsers.parse('jag anropar {verktyg} med uid "{uid}" i mappen "{mailbox}"'),
    target_fixture="outcome",
)
def call_with_mailbox(mock_ctx, verktyg, uid, mailbox):
    result = asyncio.run(_tool(verktyg).run(_args(verktyg, uid, mailbox), context=mock_ctx))
    return {"result": result, "verktyg": verktyg}


@when(parsers.parse("jag läser verktygsbeskrivningen för {verktyg}"), target_fixture="tool")
def read_tool(verktyg):
    return _tool(verktyg)


@then("ska anropet avvisas för att mailbox saknas")
def rejected(outcome):
    assert "error" in outcome, f"anropet lyckades: {outcome}"
    assert "mailbox" in str(outcome["error"])


@then("ska inget brev ha ändrats")
def nothing_changed(mock_ctx):
    imap = _imap(mock_ctx)
    for call in set(_IMAP_CALL.values()):
        getattr(imap, call).assert_not_called()


@then(parsers.parse('ska ändringen gälla brevet med UID "{uid}" i "{mailbox}"'))
def applied_in_mailbox(mock_ctx, outcome, uid, mailbox):
    call = getattr(_imap(mock_ctx), _IMAP_CALL[outcome["verktyg"]])
    call.assert_called_once()
    assert call.call_args.args[:2] == (mailbox, uid)


@then("ska mailbox vara obligatorisk utan standardvärde")
def mailbox_required(tool):
    assert "mailbox" in tool.parameters["required"]
    assert "default" not in tool.parameters["properties"]["mailbox"]


@then("ska beskrivningen säga att UID:t gäller per mapp")
def describes_per_mailbox(tool):
    assert "gäller per mapp" in tool.description
    assert "list_emails" in tool.description or "listningen" in tool.description


@then(parsers.parse('ska mailbox ha standardvärdet "{default}"'))
def mailbox_default(tool, default):
    assert tool.parameters["properties"]["mailbox"]["default"] == default

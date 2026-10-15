"""BDD: brevlådan som MCP-resurser, sett via MCP-klienten (mcp-resurser)."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import resources
from tests.mcp_resurser_support import (
    RAW_EMAIL,
    client_session,
    fake_imap,
    imap_protocol_mock,
    read_or_error,
)

scenarios("mcp_resurser.feature")


@pytest.fixture
def state():
    return {"imap": fake_imap()}


def _run(monkeypatch, state, action):
    async def run():
        async with client_session(monkeypatch, imap=state["imap"]) as session:
            return await action(session)

    return asyncio.run(run())


def _read(monkeypatch, state, uri):
    state["uri"] = uri
    text, error = _run(monkeypatch, state, lambda s: read_or_error(s, uri))
    if error is not None:
        state["error"] = error
    else:
        state["text"] = text


def _message(uid: str) -> dict:
    return {"uid": uid, "from": "anna@example.com", "subject": "Hej", "date": "", "flags": []}


# --- Given ---------------------------------------------------------------


@given(parsers.parse('att brevlådan har mapparna "{first}" och "{second}"'))
def has_mailboxes(state, first, second):
    state["imap"].list_mailboxes.return_value = [
        {"name": name, "type": "system", "selectable": True, "special_use": None}
        for name in (first, second)
    ]


@given(parsers.parse('att mappen "{mailbox}" har {total:d} mejl varav {unseen:d} olästa'))
def mailbox_has(state, mailbox, total, unseen):
    state["imap"].get_mailbox_status.return_value = {"messages": total, "unseen": unseen}
    state["imap"].list_messages.return_value = {
        "messages": [_message(str(uid)) for uid in range(total, 0, -1)],
        "total": total,
        "page": 1,
        "pages": 1,
        "has_more": False,
    }


@given(parsers.parse('att mappen "{mailbox}" inte finns'))
def mailbox_missing(state, mailbox):
    state["imap"].get_mailbox_status.side_effect = ValueError(
        f"Mappen finns inte eller kan inte läsas: {mailbox!r} (NO)"
    )


@given(parsers.parse('att mejlet med UID {uid} i "{mailbox}" finns'))
def email_exists(state, uid, mailbox):
    state["imap"].get_message.return_value = RAW_EMAIL


@given(parsers.parse('att mejlet med UID {uid} i "{mailbox}" inte finns'))
def email_missing(state, uid, mailbox):
    state["imap"].get_message.return_value = None


@given(parsers.parse('en IMAP-anslutning där mejlet med UID {uid} i "{mailbox}" finns'))
def real_imap_client(state, monkeypatch, uid, mailbox):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    from protonmail_mcp.imap_client import IMAPClient

    imap = IMAPClient(Settings())
    imap._client = imap_protocol_mock()
    raw = bytearray(RAW_EMAIL)
    imap._client.uid = AsyncMock(return_value=SimpleNamespace(
        result="OK", lines=[f"1 FETCH (UID {uid} BODY[] {{{len(raw)}}}", raw, ")", "Fetch completed"],
    ))
    state["imap"] = imap


@given("att anslutningen till Bridge nekas")
def bridge_down(state):
    state["imap"].list_mailboxes.side_effect = ConnectionRefusedError(
        61, "Connect call failed ('127.0.0.1', 1143)"
    )


# --- When ----------------------------------------------------------------


@when("klienten listar resurserna")
def list_resources(monkeypatch, state):
    async def action(session):
        return await session.list_resources(), await session.list_resource_templates()

    listed, templates = _run(monkeypatch, state, action)
    state["resources"] = [str(r.uri) for r in listed.resources]
    state["templates"] = [t.uriTemplate for t in templates.resourceTemplates]


@when(parsers.parse('klienten läser resursen "{uri}"'))
def read_uri(monkeypatch, state, uri):
    _read(monkeypatch, state, uri)


@when(parsers.parse('klienten läser mappresursen för "{mailbox}"'))
def read_mailbox(monkeypatch, state, mailbox):
    _read(monkeypatch, state, resources.mailbox_uri(mailbox))


@when(parsers.parse('klienten läser mejlresursen för UID {uid} i "{mailbox}"'))
def read_email(monkeypatch, state, uid, mailbox):
    state["uid"], state["mailbox"] = uid, mailbox
    _read(monkeypatch, state, resources.email_uri(mailbox, uid))


# --- Then ----------------------------------------------------------------


@then(parsers.parse('ska resursen "{uri}" finnas'))
def resource_listed(state, uri):
    assert uri in state["resources"]


@then(parsers.parse('ska resursmallen "{template}" finnas'))
def template_listed(state, template):
    assert template in state["templates"]


@then(parsers.parse('ska innehållet vara JSON med mappen "{mailbox}"'))
def json_with_mailbox(state, mailbox):
    assert "error" not in state, state.get("error")
    data = json.loads(state["text"])
    assert mailbox in [m["name"] for m in data["mailboxes"]]


@then(parsers.parse('ska URI:n vara "{uri}"'))
def uri_is(state, uri):
    assert state["uri"] == uri


@then(parsers.parse('ska mappen "{mailbox}" ha lästs från Bridge'))
def mailbox_read(state, mailbox):
    assert "error" not in state, state.get("error")
    state["imap"].get_mailbox_status.assert_awaited_with(mailbox)
    assert state["imap"].list_messages.await_args.args[0] == mailbox


@then(parsers.parse("ska innehållet visa {total:d} mejl varav {unseen:d} olästa"))
def shows_counts(state, total, unseen):
    data = json.loads(state["text"])
    assert (data["messages"], data["unseen"]) == (total, unseen)


@then(parsers.parse('ska innehållet lista de senaste mejlen med mappen "{mailbox}"'))
def lists_recent(state, mailbox):
    data = json.loads(state["text"])
    assert data["mailbox"] == mailbox
    assert data["recent"], "inga mejl i recent"
    for message in data["recent"]:
        assert message["mailbox"] == mailbox
        assert message["uri"] == resources.email_uri(mailbox, message["uid"])


@then("ska de senaste mejlen ha hämtats med högst 20 per sida")
def at_most_20(state):
    kwargs = state["imap"].list_messages.await_args.kwargs
    assert kwargs == {"page": 1, "page_size": 20}


@then(parsers.parse('ska innehållet vara samma som get_email ger med body_format "{body_format}"'))
def same_as_get_email(monkeypatch, state, body_format):
    assert "error" not in state, state.get("error")
    args = {
        "uid": state["uid"],
        "mailbox": state["mailbox"],
        "body_format": body_format,
        "max_length": resources.EMAIL_MAX_LENGTH,
    }
    tool_result = _run(monkeypatch, state, lambda s: s.call_tool("get_email", args))
    expected = json.loads(tool_result.content[0].text)
    assert json.loads(state["text"]) == expected


@then(parsers.parse('ska mejlet ha hämtats från mappen "{mailbox}"'))
def fetched_from(state, mailbox):
    state["imap"].get_message.assert_awaited_with(mailbox, state["uid"])


@then("ska mejlet inte ha markerats som läst")
def not_marked_read(state):
    state["imap"].set_flags.assert_not_awaited()


@then("ska mejlet ha hämtats med BODY.PEEK")
def fetched_with_peek(state):
    assert "error" not in state, state.get("error")
    calls = state["imap"]._client.uid.await_args_list
    assert calls, "inget UID-kommando skickades"
    for call in calls:
        assert call.args[0].lower() == "fetch"
        assert all("BODY[" not in str(a) or "BODY.PEEK[" in str(a) for a in call.args)


@then("ska inga flaggor ha ändrats")
def no_flags_changed(state):
    client = state["imap"]._client
    client.store.assert_not_awaited()
    for call in client.uid.await_args_list:
        assert call.args[0].lower() != "store"


@then(parsers.parse('ska läsningen misslyckas med texten "{text}"'))
def read_fails(state, text):
    assert "error" in state, f"läsningen lyckades: {state.get('text')}"
    assert text in state["error"]


@then("ska felet inte innehålla något stackspår")
def no_traceback(state):
    assert "Traceback" not in state["error"]
    assert "Error creating resource" not in state["error"]
    assert "Error reading resource" not in state["error"]


@then("ska Bridge inte ha anropats")
def bridge_untouched(state):
    assert not state["imap"].method_calls

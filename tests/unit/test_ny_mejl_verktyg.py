"""Enhetstester: check_new_emails och wait_for_new_email (ny-mejl)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_idle import MailWatcher
from protonmail_mcp.server import mcp, register_tools
from protonmail_mcp.tools import new_mail


def _ctx(app):
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app))


def _settings(**kw):
    return Settings(username="u", password="p", imap_port=1, _env_file=None, **kw)


def _poll_result(messages=(), last_uid=3, uidvalidity=1, reset=False, has_more=False, clamped=False):
    return {"messages": list(messages), "uidvalidity": uidvalidity, "last_uid": last_uid,
            "has_more": has_more, "reset": reset, "clamped": clamped}


@pytest.fixture(autouse=True)
def _clean_fallback_marks():
    new_mail._FALLBACK_MARKS.clear()
    yield
    new_mail._FALLBACK_MARKS.clear()


def test_tools_registered_read_only():
    register_tools()
    for name in ("check_new_emails", "wait_for_new_email"):
        tool = mcp._tool_manager.get_tool(name)
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert "BODY.PEEK" in tool.description or "läst" in tool.description


def test_timeout_schema_has_limits():
    register_tools()
    props = mcp._tool_manager.get_tool("wait_for_new_email").parameters["properties"]
    assert props["timeout_seconds"]["minimum"] == 1
    assert props["timeout_seconds"]["maximum"] == 300
    assert props["timeout_seconds"]["default"] == 60


async def test_invalid_mailbox_rejected_before_bridge():
    app = SimpleNamespace(imap=AsyncMock(), watcher=None)
    with pytest.raises(ValueError, match="mailbox"):
        await new_mail.check_new_emails(_ctx(app), mailbox="INBOX\r\nX")
    assert app.imap.mock_calls == []


async def test_invalid_since_uid_rejected():
    app = SimpleNamespace(imap=AsyncMock(), watcher=None)
    with pytest.raises(ValueError, match="UID"):
        await new_mail.check_new_emails(_ctx(app), mailbox="INBOX", since_uid="1:*")


async def test_without_watcher_uses_shared_client_and_module_marks():
    app = SimpleNamespace(imap=object())  # inget watcher-attribut (äldre attrapper)
    poll = AsyncMock(side_effect=[
        _poll_result(last_uid=3),
        _poll_result(messages=[{"uid": "4", "mailbox": "INBOX"}], last_uid=4),
    ])
    with patch.object(new_mail, "poll_new_messages", poll):
        first = await new_mail.check_new_emails(_ctx(app), mailbox="inbox")
        second = await new_mail.check_new_emails(_ctx(app), mailbox="INBOX")
    assert first["messages"] == [] and "Första anropet" in first["note"]
    assert poll.await_args_list[1].args[2:4] == (3, 1)  # efter UID 3, UIDVALIDITY 1
    assert [m["uid"] for m in second["messages"]] == ["4"]
    assert second["source"] == "imap" and second["watching"] is False
    assert new_mail._FALLBACK_MARKS == {"INBOX": (1, 4)}


async def test_mark_never_moves_backwards():
    watcher = MailWatcher(_settings(watch_enabled=False))
    watcher.marks["INBOX"] = (1, 10)
    app = SimpleNamespace(imap=object(), watcher=watcher)
    poll = AsyncMock(return_value=_poll_result(messages=[{"uid": "3", "mailbox": "INBOX"}], last_uid=3))
    with patch.object(new_mail, "poll_new_messages", poll):
        result = await new_mail.check_new_emails(_ctx(app), mailbox="INBOX", since_uid="2")
    assert [m["uid"] for m in result["messages"]] == ["3"]
    assert watcher.marks["INBOX"] == (1, 10)


async def test_uidvalidity_change_is_explained():
    watcher = MailWatcher(_settings(watch_enabled=False))
    watcher.marks["INBOX"] = (1, 10)
    app = SimpleNamespace(imap=object(), watcher=watcher)
    poll = AsyncMock(return_value=_poll_result(last_uid=2, uidvalidity=2, reset=True))
    with patch.object(new_mail, "poll_new_messages", poll):
        result = await new_mail.check_new_emails(_ctx(app), mailbox="INBOX")
    assert "UIDVALIDITY" in result["note"]
    assert watcher.marks["INBOX"] == (2, 2)


async def test_unwatched_mailbox_note_names_the_setting():
    watcher = MailWatcher(_settings())  # bevakar bara INBOX (inte startad här)
    app = SimpleNamespace(imap=object(), watcher=watcher)
    with patch.object(new_mail, "poll_new_messages", AsyncMock(return_value=_poll_result())):
        result = await new_mail.check_new_emails(_ctx(app), mailbox="Folders/Kunder")
    assert "PROTONMAIL_WATCH_MAILBOXES" in result["note"]


async def test_has_more_is_explained():
    app = SimpleNamespace(imap=object(), watcher=None)
    new_mail._FALLBACK_MARKS["INBOX"] = (1, 0)
    msgs = [{"uid": str(u), "mailbox": "INBOX"} for u in range(50, 0, -1)]
    with patch.object(new_mail, "poll_new_messages", AsyncMock(return_value=_poll_result(msgs, 50, has_more=True))):
        result = await new_mail.check_new_emails(_ctx(app), mailbox="INBOX")
    assert result["has_more"] is True and "igen" in result["note"]
    assert result["last_uid"] == "50"


async def test_wait_returns_bridge_error_instead_of_waiting():
    app = SimpleNamespace(imap=object(), watcher=None)
    poll = AsyncMock(side_effect=ConnectionError("Kan inte nå ProtonMail Bridge"))
    with patch.object(new_mail, "poll_new_messages", poll), pytest.raises(ConnectionError):
        await new_mail.wait_for_new_email(_ctx(app), mailbox="INBOX", timeout_seconds=60)
    assert poll.await_count == 1

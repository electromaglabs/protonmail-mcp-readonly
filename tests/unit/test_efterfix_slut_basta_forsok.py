"""G5K-5: ett fel i ett "bästa försök"-steg får inte fälla ett anrop vars huvudoperation lyckats.

- unflag_email: stjärnan är borta när Starred-steget körs. En timeout eller
  ett anslutningsfel där ska loggas och nämnas i svaret ("note"), inte bli
  ett fel för hela verktyget.
- Permanent radering efter Code=2501: en timeout i kontrollen i All Mail
  eller i återställningen ska inte kasta bort det som redan avgjorts; de mejl
  som inte gick att avgöra hamnar i failed med förklaring.
I båda fallen kastas anslutningen (protokollet är i okänt läge efter en timeout).
"""
import asyncio
from unittest.mock import MagicMock

import aioimaplib
import pytest

from protonmail_mcp import imap_bulk, imap_client, imap_labels
from protonmail_mcp.tools.labels import unflag_email
from tests.efterfix_slut_bridge import make_client


@pytest.fixture
def mock_ctx():
    return MagicMock()


@pytest.fixture
def imap_and_bridge(monkeypatch):
    monkeypatch.setattr(imap_client, "_GONE_TIMEOUT", 0.2)
    monkeypatch.setattr(imap_client, "_GONE_INTERVAL", 0.01)
    return make_client(monkeypatch)


def _fail_in(bridge, method: str, view: str, exc: BaseException, times: int = 10**9):
    mock = getattr(bridge.client, method)
    real = mock.side_effect
    left = [times]

    async def wrapper(*args, **kwargs):
        if bridge.selected == view and left[0] > 0:
            left[0] -= 1
            raise exc
        return await real(*args, **kwargs)

    mock.side_effect = wrapper


ERRORS = [
    asyncio.TimeoutError(),
    ConnectionError("Anslutningen till ProtonMail Bridge bröts"),
    aioimaplib.CommandTimeout("SEARCH"),
]


class TestUnflagStarredStep:
    @pytest.mark.parametrize("exc", ERRORS, ids=type)
    async def test_error_in_starred_step_gives_ok_with_note(self, imap_and_bridge, exc):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<a@x>", flags=("\\Flagged",))
        bridge.put("Starred", "7", "<a@x>")
        _fail_in(bridge, "search", "Starred", exc)
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res["ok"] == ["1"] and res["failed"] == []
        assert "Starred" in res["note"]
        assert "\\Flagged" not in bridge.messages["<a@x>"]["flags"]
        assert imap._client is None  # anslutningen kastas efter timeout/avbrott

    async def test_refused_starred_step_keeps_connection(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<a@x>", flags=("\\Flagged",))
        bridge.put("Starred", "7", "<a@x>")
        bridge.refuse["SEARCH"] = "SEARCH nekad"
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res["ok"] == ["1"] and "Starred" in res["note"]
        assert imap._client is bridge.client

    async def test_no_note_when_all_goes_well(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<a@x>", flags=("\\Flagged",))
        bridge.put("Starred", "7", "<a@x>")
        res = await imap_labels.set_starred(imap, "INBOX", ["1"], False)
        assert res == {"ok": ["1"], "failed": []}

    async def test_tool_returns_the_note_for_a_single_uid(self, imap_and_bridge, mock_ctx):
        imap, bridge = imap_and_bridge
        mock_ctx.request_context.lifespan_context.imap = imap
        bridge.put_mail("INBOX", "1", "<a@x>", flags=("\\Flagged",))
        bridge.put("Starred", "7", "<a@x>")
        _fail_in(bridge, "search", "Starred", asyncio.TimeoutError())
        res = await unflag_email(mock_ctx, uid="1", mailbox="INBOX")
        assert isinstance(res, dict) and res["ok"] == ["1"] and "Starred" in res["note"]

    async def test_tool_returns_true_when_nothing_to_report(self, imap_and_bridge, mock_ctx):
        imap, bridge = imap_and_bridge
        mock_ctx.request_context.lifespan_context.imap = imap
        bridge.put_mail("INBOX", "1", "<a@x>", flags=("\\Flagged",))
        assert await unflag_email(mock_ctx, uid="1", mailbox="INBOX") is True


def _two_regular(bridge):
    bridge.put_mail("Trash", "5", "<gone@x>", all_mail_uid="50")
    bridge.phantoms.add("<gone@x>")
    bridge.put_mail("Trash", "6", "<keep@x>", all_mail_uid="51")
    bridge.put_mail("Trash", "7", "<keep2@x>", all_mail_uid="52")
    bridge.no_then_vanish["Trash"] = [1, 1]


class TestPermanentDeleteChecks:
    @pytest.mark.parametrize("exc", ERRORS, ids=type)
    async def test_timeout_in_all_mail_search_is_failed_not_raised(self, imap_and_bridge, exc):
        imap, bridge = imap_and_bridge
        _two_regular(bridge)
        _fail_in(bridge, "search", "All Mail", exc)
        res = await imap_bulk.delete(imap, "Trash", ["5", "6", "7"], permanent=True)
        assert res["ok"] == []
        assert [f["uid"] for f in res["failed"]] == ["5", "6", "7"]
        assert all("All Mail" in f["error"] for f in res["failed"])
        assert imap._client is None

    async def test_connection_lost_during_recovery_keeps_earlier_results(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        _two_regular(bridge)
        real = bridge.client.uid.side_effect
        copies = []

        async def uid(command, *args):
            if command.upper() == "COPY":
                copies.append(args)
                if len(copies) == 2:
                    raise ConnectionError("Anslutningen till ProtonMail Bridge bröts")
            return await real(command, *args)

        bridge.client.uid.side_effect = uid
        res = await imap_bulk.delete(imap, "Trash", ["5", "6", "7"], permanent=True)
        assert res["ok"] == ["5", "6"]
        assert [f["uid"] for f in res["failed"]] == ["7"]
        assert "All Mail" in res["failed"][0]["error"]
        assert bridge.views_of("<keep@x>") == []
        assert imap._client is None

    async def test_timeout_while_waiting_is_failed_not_raised(self, imap_and_bridge, monkeypatch):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "6", "<keep@x>", all_mail_uid="51")
        bridge.no_then_vanish["Trash"] = [10**9, 1]
        real = bridge.client.uid.side_effect
        expunged = []

        async def uid(command, *args):
            if command.upper() == "EXPUNGE":
                expunged.append(args)
            elif command.upper() == "FETCH" and expunged and args[1] == "(UID)" and len(expunged) == 1:
                # Kontrollerna under väntan (efter -FLAGS och första kontrollen)
                if getattr(uid, "checks", 0) >= 1:
                    raise asyncio.TimeoutError()
                uid.checks = getattr(uid, "checks", 0) + 1
            return await real(command, *args)

        bridge.client.uid.side_effect = uid
        res = await imap_bulk.delete(imap, "Trash", ["6"], permanent=True)
        assert res["ok"] == []
        assert "Code=2501" in res["failed"][0]["error"]
        assert imap._client is None

    async def test_single_delete_reports_instead_of_raising_timeout(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "6", "<keep@x>", all_mail_uid="51")
        bridge.no_then_vanish["Trash"] = [1, 1]
        _fail_in(bridge, "search", "All Mail", asyncio.TimeoutError())
        with pytest.raises(ValueError, match="All Mail"):
            await imap.delete_message("Trash", "6", permanent=True)

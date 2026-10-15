"""G5K-4: väntan efter Code=2501 får inte hålla IMAP-låset och blockera andra verktyg.

Väntan (upp till _GONE_TIMEOUT = 45 s) sker utan låset; varje kontroll tar
låset, ansluter vid behov och väljer mappen igen, eftersom ett annat anrop
kan ha valt en annan mapp eller kastat anslutningen under tiden.
"""
import asyncio
import time

import pytest

from protonmail_mcp import imap_bulk, imap_client
from protonmail_mcp.imap_client import _serialized
from tests.efterfix_slut_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    monkeypatch.setattr(imap_client, "_GONE_TIMEOUT", 1.0)
    monkeypatch.setattr(imap_client, "_GONE_INTERVAL", 0.05)
    return make_client(monkeypatch)


@_serialized
async def _other_tool(imap, mailbox="INBOX"):
    await imap._ensure_connected()
    await imap._select(mailbox)
    return time.monotonic()


async def _start_delete(imap, bridge, vanish_after):
    bridge.put_mail("Trash", "5", "<a@x>", all_mail_uid="50")
    bridge.phantoms.add("<a@x>")
    bridge.no_then_vanish["Trash"] = [vanish_after, 1]
    task = asyncio.create_task(imap_bulk.delete(imap, "Trash", ["5"], permanent=True))
    # Vänta tills raderingen fått sitt NO och väntar
    for _ in range(200):
        if bridge.sent("UID EXPUNGE"):
            break
        await asyncio.sleep(0.005)
    return task


class TestOtherToolsAreNotBlocked:
    async def test_other_call_runs_during_the_wait(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "1", "<b@x>")
        task = await _start_delete(imap, bridge, 10**9)
        t0 = time.monotonic()
        got = await _other_tool(imap)
        assert got - t0 < 0.5
        assert not task.done()
        res = await task
        assert res["ok"] == [] and "finns kvar" in res["failed"][0]["error"]

    async def test_other_mailbox_selected_in_between_does_not_confuse_the_check(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.put_mail("INBOX", "5", "<b@x>")  # samma UID i en annan mapp
        task = await _start_delete(imap, bridge, 6)
        await _other_tool(imap, "INBOX")
        res = await task
        assert res == {"ok": ["5"], "failed": []}
        assert bridge.views_of("<b@x>") == ["INBOX"]

    async def test_connection_discarded_in_between_is_reconnected(self, imap_and_bridge, monkeypatch):
        imap, bridge = imap_and_bridge
        task = await _start_delete(imap, bridge, 6)

        async def reconnect():
            imap._client = bridge.client

        monkeypatch.setattr(imap, "connect", reconnect)

        @_serialized
        async def breaks_connection(self):
            self._discard_connection()

        await breaks_connection(imap)
        res = await task
        assert res == {"ok": ["5"], "failed": []}

    async def test_lock_is_free_after_cancel_during_wait(self, imap_and_bridge, monkeypatch):
        imap, bridge = imap_and_bridge

        async def reconnect():
            imap._client = bridge.client

        monkeypatch.setattr(imap, "connect", reconnect)
        task = await _start_delete(imap, bridge, 10**9)
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not imap._lock.locked()
        # Ett nytt anrop får låset direkt
        await asyncio.wait_for(_other_tool(imap), 1)

    async def test_ok_path_never_releases_the_lock(self, imap_and_bridge, monkeypatch):
        imap, bridge = imap_and_bridge
        bridge.put_mail("Trash", "5", "<a@x>")
        released = []
        real = imap._lock.release
        monkeypatch.setattr(imap._lock, "release", lambda: (released.append(1), real())[1])
        res = await imap_bulk.delete(imap, "Trash", ["5"], permanent=True)
        assert res == {"ok": ["5"], "failed": []}
        assert len(released) == 1  # bara när anropet är klart

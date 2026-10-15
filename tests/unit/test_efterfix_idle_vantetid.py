"""Enhetstester: väntetiden nollställs först när en IDLE-omgång gått klart (G4I-2)."""
import asyncio

import pytest

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_idle import MailWatcher
from tests.ny_mejl_fakeidle import FakeIdleBridge


@pytest.mark.parametrize("mode", ["no", "close"])
async def test_backoff_grows_when_idle_fails_after_login(mode):
    fake = FakeIdleBridge()
    fake.add_box("INBOX", [1])
    await fake.start()
    fake.idle_mode = mode
    delays, watching = [], []
    w = None

    async def sleep(delay):
        delays.append(delay)
        watching.append(w.is_watching("INBOX"))
        await asyncio.sleep(0)

    settings = Settings(username="u", password="p", imap_port=fake.port, imap_timeout=2, _env_file=None)
    w = MailWatcher(settings, backoff_initial=0.5, backoff_max=4, sleep=sleep)
    w.start()
    try:
        for _ in range(500):
            if len(delays) >= 6:
                break
            await asyncio.sleep(0.01)
        assert delays[:6] == [0.5, 1, 2, 4, 4, 4]
        if mode == "no":
            assert not any(watching), "IDLE nekades: mappen bevakas inte"
            assert w.status("INBOX")["last_error"] == "ProtonMail Bridge nekade IDLE"
    finally:
        await w.stop()
        await fake.stop()

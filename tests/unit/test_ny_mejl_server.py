"""Enhetstester: AppContext.watcher och lifespan (ny-mejl)."""
from unittest.mock import AsyncMock, patch

import pytest

from protonmail_mcp import config
from protonmail_mcp.config import Settings
from protonmail_mcp.imap_idle import MailWatcher
from protonmail_mcp.server import AppContext, lifespan, mcp


def test_app_context_watcher_defaults_to_none():
    app = AppContext(imap=AsyncMock(), smtp=AsyncMock())
    assert app.watcher is None


async def test_watcher_stopped_even_if_imap_disconnect_fails(tmp_path):
    settings = Settings(username="u", password="p", imap_port=1, attachment_dir=tmp_path,
                        watch_enabled=False, _env_file=None)
    with patch.object(config, "get_settings", return_value=settings), \
            patch.object(MailWatcher, "stop", new=AsyncMock()) as stop:
        with pytest.raises(RuntimeError, match="nej"):
            async with lifespan(mcp) as app:
                assert isinstance(app.watcher, MailWatcher)
                app.imap.disconnect = AsyncMock(side_effect=RuntimeError("nej"))
        stop.assert_awaited_once()


async def test_lifespan_connects_new_mail_to_resource_notifications(tmp_path):
    settings = Settings(username="u", password="p", imap_port=1, attachment_dir=tmp_path,
                        watch_enabled=False, _env_file=None)
    with patch.object(config, "get_settings", return_value=settings), \
            patch("protonmail_mcp.subscriptions.notify_resource_updated", new=AsyncMock()) as notify:
        async with lifespan(mcp) as app:
            assert len(app.watcher._listeners) == 1
            await app.watcher._notify("Folders/A/B", [{"uid": "4"}])
    notify.assert_awaited_once_with("mailbox://Folders%2FA%2FB")

"""Vilka resurser ett lyckat skrivverktyg ändrar, och efter-anrop-kroken (efterfix-resurser, R4-2)."""
import asyncio
import time

import pytest

from protonmail_mcp import subscriptions
from protonmail_mcp.server import mcp, register_tools
from protonmail_mcp.subscriptions import changed_uris


@pytest.fixture(autouse=True)
def _empty_registry():
    subscriptions.registry.clear()
    yield
    subscriptions.registry.clear()


class TestChangedUris:
    @pytest.mark.parametrize("tool", ["mark_email_read", "mark_email_unread", "flag_email", "unflag_email"])
    def test_flags_change_mailbox_and_email(self, tool):
        assert changed_uris(tool, {"uid": "42", "mailbox": "INBOX"}, True) == [
            "mailbox://INBOX", "email://INBOX/42",
        ]

    def test_bulk_only_ok_uids(self):
        result = {"ok": ["1", "3"], "failed": [{"uid": "2", "error": "x"}]}
        assert changed_uris("mark_email_read", {"uid": ["1", "2", "3"], "mailbox": "INBOX"}, result) == [
            "mailbox://INBOX", "email://INBOX/1", "email://INBOX/3",
        ]

    def test_bulk_with_nothing_ok_changes_nothing(self):
        result = {"ok": [], "failed": [{"uid": "2", "error": "x"}]}
        assert changed_uris("move_email", {"uid": ["2"], "mailbox": "INBOX", "target_mailbox": "Archive"}, result) == []

    @pytest.mark.parametrize("tool", ["add_label", "remove_label"])
    def test_labels_change_mailbox_email_and_label(self, tool):
        assert changed_uris(tool, {"uid": "7", "mailbox": "INBOX", "label": "Labels/Näs"}, True) == [
            "mailbox://INBOX", "email://INBOX/7", "mailbox://Labels%2FN%C3%A4s",
        ]

    def test_move_changes_source_target_and_email(self):
        args = {"uid": "42", "mailbox": "INBOX", "target_mailbox": "Folders/A"}
        assert changed_uris("move_email", args, True) == [
            "mailbox://INBOX", "email://INBOX/42", "mailbox://Folders%2FA",
        ]

    def test_delete_to_trash(self):
        args = {"uid": "42", "mailbox": "INBOX", "permanent": False}
        assert changed_uris("delete_email", args, True) == [
            "mailbox://INBOX", "email://INBOX/42", "mailbox://Trash",
        ]

    def test_delete_permanent_has_no_trash(self):
        args = {"uid": "42", "mailbox": "Trash", "permanent": True}
        assert changed_uris("delete_email", args, True) == ["mailbox://Trash", "email://Trash/42"]

    def test_folders(self):
        assert changed_uris("create_folder", {"name": "Folders/A"}, True) == ["mailboxes://", "mailbox://Folders%2FA"]
        assert changed_uris("delete_folder", {"name": "Folders/A", "force": True}, True) == [
            "mailboxes://", "mailbox://Folders%2FA",
        ]
        assert changed_uris("rename_folder", {"old_name": "Folders/A", "new_name": "Folders/B"}, True) == [
            "mailboxes://", "mailbox://Folders%2FA", "mailbox://Folders%2FB",
        ]

    @pytest.mark.parametrize("tool", ["create_draft", "create_reply_draft", "create_forward_draft"])
    def test_new_drafts(self, tool):
        assert changed_uris(tool, {"uid": "42", "mailbox": "INBOX"}, {"uid": "9", "mailbox": "Drafts"}) == [
            "mailbox://Drafts",
        ]

    def test_update_draft_replaces_the_old_one(self):
        assert changed_uris("update_draft", {"uid": "9", "mailbox": "Drafts"}, {"uid": "10"}) == [
            "mailbox://Drafts", "email://Drafts/9", "mailbox://Trash",
        ]

    def test_send_draft(self):
        assert changed_uris("send_draft", {"uid": "9", "mailbox": "Drafts"}, {"sent": True}) == [
            "mailbox://Drafts", "email://Drafts/9", "mailbox://Sent",
        ]

    @pytest.mark.parametrize("tool", ["send_email", "reply_to_email", "forward_email"])
    def test_sending_changes_sent(self, tool):
        assert changed_uris(tool, {"uid": "42", "mailbox": "INBOX"}, True) == ["mailbox://Sent"]

    @pytest.mark.parametrize("tool", ["list_emails", "get_email", "get_attachment", "okänt_verktyg"])
    def test_other_tools_change_nothing(self, tool):
        assert changed_uris(tool, {"uid": "42", "mailbox": "INBOX"}, True) == []

    def test_false_result_changes_nothing(self):
        assert changed_uris("create_folder", {"name": "A"}, False) == []

    def test_invalid_names_are_skipped_not_raised(self):
        assert changed_uris("create_folder", {"name": None}, True) == ["mailboxes://"]


def test_every_writing_tool_is_classified():
    """Ett nytt skrivverktyg måste tas ställning till: vilka resurser ändrar det?"""
    register_tools()
    writing = {
        t.name for t in mcp._tool_manager.list_tools()
        if not (t.annotations and t.annotations.readOnlyHint)
    }
    unclassified = writing - set(subscriptions.TOOL_CHANGES) - subscriptions.TOOLS_WITHOUT_MAILBOX_CHANGES
    assert unclassified == set(), (
        "Lägg till verktygen i subscriptions.TOOL_CHANGES (vilka resurser de ändrar) "
        f"eller i TOOLS_WITHOUT_MAILBOX_CHANGES: {sorted(unclassified)}"
    )


class TestHook:
    def test_registered_writing_tool_is_wrapped_with_the_hook(self):
        register_tools()
        fn = mcp._tool_manager.get_tool("mark_email_read").fn
        assert getattr(fn, "_notifies_subscribers", False) is True

    def test_read_only_tools_are_not_wrapped(self):
        register_tools()
        fn = mcp._tool_manager.get_tool("list_emails").fn
        assert not getattr(fn, "_notifies_subscribers", False)

    def test_hook_does_not_wait_for_notifications(self, monkeypatch):
        from protonmail_mcp.tools import notify_after

        started = asyncio.Event()

        async def slow(uri):
            started.set()
            await asyncio.sleep(10)

        monkeypatch.setattr(subscriptions, "notify_resource_updated", slow)
        subscriptions.registry.subscribe(object(), "mailbox://INBOX")

        async def mark_email_read(ctx, uid, mailbox):
            return True

        async def run():
            wrapped = notify_after(mark_email_read, "mark_email_read")
            t0 = time.monotonic()
            assert await wrapped(None, uid="42", mailbox="INBOX") is True
            elapsed = time.monotonic() - t0
            await asyncio.wait_for(started.wait(), 1)  # notisen startade i bakgrunden
            for task in list(subscriptions._pending):
                task.cancel()
            return elapsed

        assert asyncio.run(run()) < 0.5

    def test_hook_passes_errors_through_and_notifies_nothing(self, monkeypatch):
        from protonmail_mcp.tools import notify_after

        calls = []
        monkeypatch.setattr(subscriptions, "notify_soon", lambda uris: calls.append(uris))

        async def move_email(ctx, uid, target_mailbox, mailbox):
            raise ValueError("Bridge nekade")

        with pytest.raises(ValueError, match="Bridge nekade"):
            asyncio.run(notify_after(move_email, "move_email")(None, uid="1", target_mailbox="A", mailbox="INBOX"))
        assert calls == []

    def test_hook_uses_defaults_and_positional_arguments(self, monkeypatch):
        from protonmail_mcp.tools import notify_after

        calls = []
        monkeypatch.setattr(subscriptions, "notify_soon", lambda uris: calls.append(uris))

        async def delete_email(ctx, uid, mailbox, permanent=False):
            return True

        asyncio.run(notify_after(delete_email, "delete_email")(None, "42", "INBOX"))
        assert calls == [["mailbox://INBOX", "email://INBOX/42", "mailbox://Trash"]]

    def test_hook_failure_never_breaks_the_tool(self, monkeypatch):
        from protonmail_mcp.tools import notify_after

        def broken(*a, **k):
            raise RuntimeError("trasig krok")

        monkeypatch.setattr(subscriptions, "changed_uris", broken)

        async def create_folder(ctx, name):
            return True

        assert asyncio.run(notify_after(create_folder, "create_folder")(None, name="A")) is True

    def test_signature_is_kept_for_the_schema(self):
        import inspect

        from protonmail_mcp.tools import notify_after

        async def create_folder(ctx, name: str) -> bool:
            """Doc."""
            return True

        wrapped = notify_after(create_folder, "create_folder")
        assert inspect.signature(wrapped) == inspect.signature(create_folder)
        assert wrapped.__doc__ == "Doc."


class TestNotifySoon:
    def test_nothing_is_scheduled_without_subscribers(self):
        async def run():
            subscriptions.notify_soon(["mailbox://INBOX"])
            return len(subscriptions._pending)

        assert asyncio.run(run()) == 0

    def test_scheduled_notice_reaches_the_subscriber(self):
        class S:
            def __init__(self):
                self.sent = []

            async def send_resource_updated(self, uri):
                self.sent.append(str(uri))

        s = S()
        subscriptions.registry.subscribe(s, "mailbox://inbox")

        async def run():
            subscriptions.notify_soon(["mailbox://INBOX", "email://INBOX/1"])
            await subscriptions.wait_for_pending_notices()

        asyncio.run(run())
        assert s.sent == ["mailbox://inbox"]


class TestSubscribeNote:
    """Prenumeration godtas alltid; loggen säger när bara egna verktyg ger notis."""

    @pytest.fixture(autouse=True)
    def _settings(self, monkeypatch):
        from protonmail_mcp import config

        monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
        monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
        monkeypatch.setenv("PROTONMAIL_WATCH_MAILBOXES", "INBOX,Folders/Kunder")
        settings = config.Settings()
        monkeypatch.setattr(config, "get_settings", lambda: settings)

    @pytest.mark.parametrize("uri", ["mailbox://INBOX", "mailbox://inbox", "mailbox://Folders%2FKunder"])
    def test_watched_mailbox_has_no_note(self, uri):
        assert subscriptions.coverage_note(uri) is None

    def test_unwatched_mailbox_is_noted(self):
        note = subscriptions.coverage_note("mailbox://Archive")
        assert "PROTONMAIL_WATCH_MAILBOXES" in note and "serverns egna verktyg" in note

    @pytest.mark.parametrize("uri", ["email://INBOX/42", "mailboxes://"])
    def test_email_and_mailbox_list_are_noted(self, uri):
        assert "serverns egna verktyg" in subscriptions.coverage_note(uri)

    def test_note_never_raises_without_settings(self, monkeypatch):
        from protonmail_mcp import config

        def broken():
            raise RuntimeError("ingen konfiguration")

        monkeypatch.setattr(config, "get_settings", broken)
        assert "serverns egna verktyg" in subscriptions.coverage_note("mailbox://Archive")

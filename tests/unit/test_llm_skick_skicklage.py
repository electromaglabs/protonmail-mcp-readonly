"""PROTONMAIL_SEND_MODE: send (standard), draft_only och disabled."""
import email
import email.policy
from email.message import EmailMessage

import pytest
from pydantic import ValidationError

from protonmail_mcp import imap_drafts, policy
from protonmail_mcp.smtp_client import SMTPClient
from tests.llm_skick_support import BridgeSpy, call_tool, make_app, make_settings, spy_imap, spy_smtp_patch
from tests.sdk_support import ToolError

SEND_TOOLS = ["send_email", "reply_to_email", "forward_email", "send_draft"]
DRAFT_TOOLS = ["create_draft", "create_reply_draft", "create_forward_draft", "update_draft"]


def _draft_bytes() -> bytes:
    msg = EmailMessage()
    msg["To"] = "anna@exempel.se"
    msg["Subject"] = "Hej"
    msg.set_content("Hej")
    return msg.as_bytes()


def test_default_is_send():
    assert make_settings().send_mode == "send"


def test_invalid_mode_rejected():
    with pytest.raises(ValidationError):
        make_settings(send_mode="ibland")


@pytest.mark.parametrize("raw", ["DRAFT_ONLY", " draft_only ", "Draft_Only"])
def test_mode_is_case_and_space_insensitive(raw):
    assert make_settings(send_mode=raw).send_mode == "draft_only"


def test_mode_from_environment(monkeypatch):
    from protonmail_mcp.config import Settings

    monkeypatch.setenv("PROTONMAIL_SEND_MODE", "disabled")
    assert Settings(username="u", password="p", _env_file=None).send_mode == "disabled"


@pytest.mark.parametrize("tool", SEND_TOOLS)
async def test_draft_only_refuses_send_tools_with_hint(tool):
    settings = make_settings(send_mode="draft_only")
    spy = BridgeSpy()
    with spy_smtp_patch(spy), pytest.raises(ToolError) as exc:
        await call_tool(tool, {}, make_app(settings, spy), settings)
    text = str(exc.value)
    assert "PROTONMAIL_SEND_MODE=draft_only" in text
    for hint in ("create_draft", "create_reply_draft", "create_forward_draft"):
        assert hint in text
    assert not spy.contacted


@pytest.mark.parametrize("tool", DRAFT_TOOLS)
def test_draft_only_lets_draft_tools_through(tool):
    policy.check_tool(make_settings(send_mode="draft_only"), tool)  # kastar inte


@pytest.mark.parametrize("tool", SEND_TOOLS + DRAFT_TOOLS)
async def test_disabled_refuses_send_and_draft_tools(tool):
    settings = make_settings(send_mode="disabled")
    spy = BridgeSpy()
    with spy_smtp_patch(spy), pytest.raises(ToolError, match="PROTONMAIL_SEND_MODE=disabled"):
        await call_tool(tool, {}, make_app(settings, spy), settings)
    assert not spy.contacted


@pytest.mark.parametrize("tool", ["move_email", "delete_email", "mark_email_read", "add_label", "create_folder"])
def test_send_mode_does_not_affect_other_writes(tool):
    for mode in ("draft_only", "disabled"):
        policy.check_tool(make_settings(send_mode=mode), tool)  # kastar inte


@pytest.mark.parametrize("mode", ["draft_only", "disabled"])
async def test_smtp_send_email_refused(mode):
    spy = BridgeSpy()
    smtp = SMTPClient(make_settings(send_mode=mode))
    with spy_smtp_patch(spy), pytest.raises(ValueError, match=f"PROTONMAIL_SEND_MODE={mode}"):
        await smtp.send_email(to="anna@exempel.se", subject="Hej", body="Hej")
    assert spy.smtp_connections == 0


@pytest.mark.parametrize("mode", ["draft_only", "disabled"])
async def test_smtp_send_prepared_message_refused(mode):
    spy = BridgeSpy()
    smtp = SMTPClient(make_settings(send_mode=mode))
    msg = email.message_from_bytes(_draft_bytes(), policy=email.policy.SMTP)
    with spy_smtp_patch(spy), pytest.raises(ValueError, match=f"PROTONMAIL_SEND_MODE={mode}"):
        await smtp.send_prepared_message(msg)
    assert spy.smtp_connections == 0


@pytest.mark.parametrize(
    "call",
    [
        lambda imap: imap_drafts.append_draft(imap, _draft_bytes(), "<a@b>"),
        lambda imap: imap_drafts.replace_draft(imap, "7", _draft_bytes(), "<a@b>"),
    ],
    ids=["append_draft", "replace_draft"],
)
async def test_disabled_refuses_drafts_in_imap_without_contact(call):
    spy = BridgeSpy()
    imap = spy_imap(make_settings(send_mode="disabled"), spy)
    with pytest.raises(ValueError, match="PROTONMAIL_SEND_MODE=disabled"):
        await call(imap)
    assert spy.imap_calls == []


async def test_draft_only_allows_append_draft(monkeypatch):
    spy = BridgeSpy()
    imap = spy_imap(make_settings(send_mode="draft_only"), spy)

    async def connected():
        return None

    async def store(imap, message, message_id):
        return "12"

    imap._ensure_connected = connected
    monkeypatch.setattr(imap_drafts, "_store_draft", store)
    assert await imap_drafts.append_draft(imap, _draft_bytes(), "<a@b>") == "12"


def test_send_mode_does_not_block_plain_deletes():
    """remove_sent_draft är en radering, inte ett utkast: skickläget rör den inte."""
    policy.require_write(make_settings(send_mode="disabled"), "remove_sent_draft")  # kastar inte

"""PROTONMAIL_READ_ONLY: inget verktyg och ingen skrivfunktion får nå Bridge.

Två lager testas var för sig:
1. Verktygen genom MCP-servern (mcp.call_tool): varje verktyg som inte är rent
   läsande vägras innan något når Bridge. Listorna nedan är medvetet
   explicita — ett nytt verktyg får testet att falla tills det placerats i
   rätt lista.
2. Skrivfunktionerna i IMAP- och SMTP-klienten anropade direkt: även ett
   verktyg som glömt policyn kan inte skriva eller skicka.
"""
from email.message import EmailMessage

import pytest

from protonmail_mcp import imap_bulk, imap_drafts, imap_labels
from protonmail_mcp.smtp_client import SMTPClient
from tests.llm_skick_support import (
    BridgeSpy,
    call_tool,
    make_app,
    make_settings,
    registered_tools,
    spy_imap,
    spy_smtp_patch,
)

# Rent läsande verktyg: ändrar ingenting i kontot.
READ_TOOLS = {
    "list_mailboxes",
    "get_mailbox_status",
    "list_emails",
    "get_email",
    "get_email_headers",
    "search_emails",
    "get_thread",
    "get_attachment",
    "check_new_emails",
    "wait_for_new_email",
}

# Verktyg som skriver i kontot eller skickar.
WRITE_TOOLS = {
    "mark_email_read",
    "mark_email_unread",
    "move_email",
    "delete_email",
    "create_folder",
    "delete_folder",
    "rename_folder",
    "add_label",
    "remove_label",
    "flag_email",
    "unflag_email",
    "create_draft",
    "create_reply_draft",
    "create_forward_draft",
    "update_draft",
    "send_draft",
    "send_email",
    "reply_to_email",
    "forward_email",
}


def test_every_registered_tool_is_classified():
    tools = registered_tools()
    assert tools - READ_TOOLS - WRITE_TOOLS == set(), "nytt verktyg: lägg det i READ_TOOLS eller WRITE_TOOLS"
    assert (READ_TOOLS | WRITE_TOOLS) - tools == set(), "verktyget finns inte längre"
    assert not READ_TOOLS & WRITE_TOOLS


@pytest.mark.parametrize("tool", sorted(WRITE_TOOLS))
async def test_write_tool_refused_before_bridge(tool):
    settings = make_settings(read_only=True)
    spy = BridgeSpy()
    app = make_app(settings, spy)
    with spy_smtp_patch(spy):
        with pytest.raises(ValueError, match="PROTONMAIL_READ_ONLY"):
            # Argumenten spelar ingen roll: vägran kommer före tolkningen
            await call_tool(tool, {}, app, settings)
    assert not spy.contacted, (spy.imap_calls, spy.smtp_connections)


@pytest.mark.parametrize("tool", sorted(READ_TOOLS))
async def test_read_tool_not_refused(tool):
    settings = make_settings(read_only=True)
    spy = BridgeSpy()
    app = make_app(settings, spy)
    try:
        await call_tool(tool, {}, app, settings)
    except Exception as exc:  # noqa: BLE001 — argumenten saknas, men vägran får inte komma från policyn
        assert "PROTONMAIL_READ_ONLY" not in str(exc)


def test_read_only_defaults_to_false():
    assert make_settings().read_only is False


# --- Lager 2: skrivfunktionerna direkt -------------------------------------

def _draft() -> bytes:
    msg = EmailMessage()
    msg["To"] = "anna@exempel.se"
    msg["Subject"] = "Hej"
    msg.set_content("Hej")
    return msg.as_bytes()


IMAP_WRITES = {
    "IMAPClient.set_flags": lambda imap: imap.set_flags("INBOX", "5", r"(\Seen)", add=True),
    "IMAPClient.move_message": lambda imap: imap.move_message("INBOX", "5", "Archive"),
    "IMAPClient.delete_message": lambda imap: imap.delete_message("INBOX", "5"),
    "IMAPClient.delete_message permanent": lambda imap: imap.delete_message("Trash", "5", permanent=True),
    "IMAPClient.create_folder": lambda imap: imap.create_folder("Folders/Ny"),
    "IMAPClient.delete_folder": lambda imap: imap.delete_folder("Folders/Ny"),
    "IMAPClient.rename_folder": lambda imap: imap.rename_folder("Folders/Ny", "Folders/Nyare"),
    "imap_bulk.set_flags": lambda imap: imap_bulk.set_flags(imap, "INBOX", ["5", "6"], r"(\Seen)", add=False),
    "imap_bulk.move": lambda imap: imap_bulk.move(imap, "INBOX", ["5", "6"], "Archive"),
    "imap_bulk.delete": lambda imap: imap_bulk.delete(imap, "INBOX", ["5", "6"]),
    "imap_labels.add_label": lambda imap: imap_labels.add_label(imap, "INBOX", ["5"], "Arbete"),
    "imap_labels.remove_label": lambda imap: imap_labels.remove_label(imap, "INBOX", ["5"], "Arbete"),
    "imap_labels.set_starred": lambda imap: imap_labels.set_starred(imap, "INBOX", ["5"], True),
    "imap_drafts.append_draft": lambda imap: imap_drafts.append_draft(imap, _draft(), "<a@b>"),
    "imap_drafts.replace_draft": lambda imap: imap_drafts.replace_draft(imap, "7", _draft(), "<a@b>"),
    "imap_drafts.remove_sent_draft": lambda imap: imap_drafts.remove_sent_draft(imap, "7"),
}


@pytest.mark.parametrize("name", sorted(IMAP_WRITES))
async def test_imap_write_refused_without_contact(name):
    spy = BridgeSpy()
    imap = spy_imap(make_settings(read_only=True), spy)
    with pytest.raises(ValueError, match="PROTONMAIL_READ_ONLY"):
        await IMAP_WRITES[name](imap)
    assert spy.imap_calls == []


async def test_imap_write_refusal_does_not_validate_first():
    """Vägran kommer först, även för ett ogiltigt anrop — inget tolkas eller skickas."""
    spy = BridgeSpy()
    imap = spy_imap(make_settings(read_only=True), spy)
    with pytest.raises(ValueError, match="PROTONMAIL_READ_ONLY"):
        await imap.move_message("INBOX", "inte-ett-uid", "Archive")


async def test_smtp_send_email_refused_without_contact():
    spy = BridgeSpy()
    smtp = SMTPClient(make_settings(read_only=True))
    with spy_smtp_patch(spy), pytest.raises(ValueError, match="PROTONMAIL_READ_ONLY"):
        await smtp.send_email(to="anna@exempel.se", subject="Hej", body="Hej")
    assert spy.smtp_connections == 0


async def test_smtp_send_prepared_message_refused_without_contact():
    import email
    import email.policy

    spy = BridgeSpy()
    smtp = SMTPClient(make_settings(read_only=True))
    msg = email.message_from_bytes(_draft(), policy=email.policy.SMTP)
    with spy_smtp_patch(spy), pytest.raises(ValueError, match="PROTONMAIL_READ_ONLY"):
        await smtp.send_prepared_message(msg)
    assert spy.smtp_connections == 0


async def test_read_only_from_environment(monkeypatch):
    from protonmail_mcp.config import Settings

    monkeypatch.setenv("PROTONMAIL_READ_ONLY", "true")
    assert Settings(username="u", password="p", _env_file=None).read_only is True

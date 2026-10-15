"""Begränsningar av vad servern (och därmed en LLM) får göra med kontot.

Inställningarna (PROTONMAIL_READ_ONLY m.fl., se config.py) kontrolleras
centralt, så att inget verktyg kan glömma dem:

- IMAPClient-metoderna och modulfunktionerna som skriver (flaggor, flytt,
  radering, etiketter, mappar, utkast) är dekorerade med ``write_operation``,
  som vägrar innan Bridge kontaktas.
- SMTPClient kontrollerar skickpolicyn i den gemensamma leveransvägen.
- MCP-servern (server.py) vägrar dessutom verktyg efter namn innan de körs,
  så att ett verktyg som först läser originalet (t.ex. reply_to_email) inte
  ens läser när skicket ändå skulle vägras.

Alla vägringar är ValueError med en text som når klienten oförändrad.
"""
from __future__ import annotations

import functools
from typing import Any

# Verktygen per kategori. Används av MCP-servern för att vägra tidigt; den
# egentliga spärren sitter i klienterna. Ett verktyg som saknas här
# släpps igenom till klienternas spärrar (tests/unit/test_llm_skick_skrivskydd.py
# kräver att varje registrerat verktyg finns i sin lista där).
WRITE_TOOLS = frozenset({
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
})
DRAFT_TOOLS = frozenset({
    "create_draft",
    "create_reply_draft",
    "create_forward_draft",
    "update_draft",
})
SEND_TOOLS = frozenset({
    "send_email",
    "reply_to_email",
    "forward_email",
    "send_draft",
})


def _read_only(settings: Any) -> bool:
    # "is True": en attrapp (MagicMock) som settings ska inte räknas som påslagen
    return getattr(settings, "read_only", False) is True


def require_write(settings: Any, action: str) -> None:
    """ValueError om kontot är skrivskyddat (PROTONMAIL_READ_ONLY=true)."""
    if _read_only(settings):
        raise ValueError(
            f"Kontot är skrivskyddat för den här servern (PROTONMAIL_READ_ONLY=true), "
            f"så {action} vägras. Inget har ändrats eller skickats."
        )


def require_send(settings: Any, action: str) -> None:
    """ValueError om skick inte är tillåtet."""
    require_write(settings, action)


def require_draft(settings: Any, action: str) -> None:
    """ValueError om utkast inte får skapas eller ändras."""
    require_write(settings, action)


def check_tool(settings: Any, tool: str) -> None:
    """Vägra ett verktyg efter namn, innan det körs (anropas av MCP-servern)."""
    if tool in SEND_TOOLS:
        require_send(settings, tool)
    elif tool in DRAFT_TOOLS:
        require_draft(settings, tool)
    elif tool in WRITE_TOOLS:
        require_write(settings, tool)


def write_operation(action: str, *, draft: bool = False):
    """Dekorator för IMAP-funktioner som skriver i kontot.

    Den dekorerade funktionens första argument är IMAPClient (``self`` eller
    ``imap``); policyn läses ur dess ``_settings``. Kontrollen görs innan
    funktionen körs, alltså innan något valideras eller skickas till Bridge.
    Lägg dekoratorn närmast funktionen (under ``_serialized``), så att även
    anrop via ``__wrapped__`` (utan lås) kontrolleras.
    """
    check = require_draft if draft else require_write

    def decorate(func):
        @functools.wraps(func)
        async def wrapper(imap, *args, **kwargs):
            check(getattr(imap, "_settings", None), action)
            return await func(imap, *args, **kwargs)
        return wrapper
    return decorate

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
import math
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Callable

from .config import normalize_domain, parse_allowed_recipients

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


_DRAFT_HINT = (
    "Skapa ett utkast i stället med create_draft, create_reply_draft eller "
    "create_forward_draft, så kan användaren granska och skicka det själv i Proton."
)


def _send_mode(settings: Any) -> str:
    mode = getattr(settings, "send_mode", "send")
    return mode if mode in ("send", "draft_only", "disabled") else "send"


def require_send(settings: Any, action: str) -> None:
    """ValueError om skick inte är tillåtet (skrivskydd eller PROTONMAIL_SEND_MODE)."""
    require_write(settings, action)
    mode = _send_mode(settings)
    if mode == "draft_only":
        raise ValueError(
            f"Servern får inte skicka e-post (PROTONMAIL_SEND_MODE=draft_only), så "
            f"{action} vägras och inget skickades. {_DRAFT_HINT}"
        )
    if mode == "disabled":
        raise ValueError(
            f"Servern får varken skicka e-post eller skapa utkast "
            f"(PROTONMAIL_SEND_MODE=disabled), så {action} vägras och inget skickades."
        )


def require_draft(settings: Any, action: str) -> None:
    """ValueError om utkast inte får skapas eller ändras (skrivskydd eller disabled)."""
    require_write(settings, action)
    if _send_mode(settings) == "disabled":
        raise ValueError(
            f"Servern får varken skicka e-post eller skapa utkast "
            f"(PROTONMAIL_SEND_MODE=disabled), så {action} vägras. Inget har sparats."
        )


def check_tool(settings: Any, tool: str) -> None:
    """Vägra ett verktyg efter namn, innan det körs (anropas av MCP-servern)."""
    if tool in SEND_TOOLS:
        require_send(settings, tool)
    elif tool in DRAFT_TOOLS:
        require_draft(settings, tool)
    elif tool in WRITE_TOOLS:
        require_write(settings, tool)


def _is_allowed(address: str, rules: tuple[tuple[str, str], ...]) -> bool:
    local, _, domain = address.rpartition("@")
    normalized = normalize_domain(domain)
    if not local or normalized is None:
        return False
    return ("", normalized) in rules or (local, normalized) in rules


def check_recipients(settings: Any, recipients: list[str]) -> None:
    """ValueError om någon mottagare inte är tillåten. Inget skickas då."""
    raw = getattr(settings, "allowed_recipients", "")
    rules = parse_allowed_recipients(raw) if isinstance(raw, str) else ()
    if not rules:
        return
    refused: list[str] = []
    for address in recipients:
        if not _is_allowed(address, rules) and address not in refused:
            refused.append(address)
    if refused:
        raise ValueError(
            f"Skicket vägrades: {', '.join(refused)} finns inte bland de tillåtna "
            f"mottagarna (PROTONMAIL_ALLOWED_RECIPIENTS). Inget mejl skickades till någon."
        )


def _limit(settings: Any, name: str) -> int:
    value = getattr(settings, name, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def check_recipient_count(settings: Any, recipients: list[str]) -> None:
    """ValueError om skicket har fler unika mottagare än PROTONMAIL_MAX_RECIPIENTS."""
    limit = _limit(settings, "max_recipients")
    count = len({address.lower() for address in recipients})
    if limit and count > limit:
        raise ValueError(
            f"Skicket vägrades: {count} mottagare, men högst {limit} per mejl är tillåtet "
            f"(PROTONMAIL_MAX_RECIPIENTS). Inget mejl skickades."
        )


_WINDOW = 3600.0


def _wait_text(seconds: float) -> str:
    if seconds >= 60:
        minutes = math.ceil(seconds / 60)
        return f"om {minutes} minut{'er' if minutes != 1 else ''}"
    whole = max(1, math.ceil(seconds))
    return f"om {whole} sekund{'er' if whole != 1 else ''}"


class SendRateLimiter:
    """Högst PROTONMAIL_MAX_SENDS_PER_HOUR skick under en glidande timme.

    Räknaren ligger i minnet. ``acquire`` kontrollerar och räknar skicket i
    ett svep (utan await emellan, så samtidiga anrop kan inte smita förbi).
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._times: deque[float] = deque()

    def acquire(self, settings: Any) -> None:
        limit = _limit(settings, "max_sends_per_hour")
        if not limit:
            return
        now = self._clock()
        while self._times and now - self._times[0] >= _WINDOW:
            self._times.popleft()
        if len(self._times) >= limit:
            wait = self._times[-limit] + _WINDOW - now
            at = (datetime.now() + timedelta(seconds=wait)).strftime("%H:%M:%S")
            raise ValueError(
                f"Skicket vägrades: högst {limit} skick per timme är tillåtet "
                f"(PROTONMAIL_MAX_SENDS_PER_HOUR), och gränsen är nådd. Nästa skick går "
                f"{_wait_text(wait)} (kl. {at}). Inget mejl skickades."
            )
        self._times.append(now)


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

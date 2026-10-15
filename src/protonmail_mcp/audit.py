"""Granskningslogg: en JSON-rad för varje skick och varje skrivande IMAP-operation.

Raden har tid (UTC), verktyg (om anropet kom från ett MCP-verktyg), åtgärd,
mapp, UID:n, mottagaradresser, Message-ID och resultat ("ok"/"error", med
felet). Den innehåller ALDRIG ämne, brödtext, bilagor eller lösenord: bara
fälten som anges uttryckligen till ``record`` skrivs.

Raden loggas alltid på INFO till loggern ``protonmail_mcp.audit`` (stderr),
men där med mottagaradresserna ersatta av ett antal och adresser i feltexten
maskerade — stderr sparas ofta i klientens loggfil, och Bcc ska förbli hemligt.
Den fullständiga raden läggs i filen PROTONMAIL_AUDIT_LOG om den är satt. Filen
skapas med rättigheterna 0600 och öppnas aldrig genom en symlänk. Går filen
inte att skriva loggas en varning; operationen påverkas inte.
"""
from __future__ import annotations

import json
import logging
import os
import re
import stat
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("protonmail_mcp.audit")
logger.setLevel(logging.INFO)

# Namnet på MCP-verktyget som körs just nu (sätts av servern runt varje anrop)
current_tool: ContextVar[str | None] = ContextVar("protonmail_mcp_current_tool", default=None)

_MAX_ERROR_CHARS = 500

# Adresser i feltexter på stderr (t.ex. "hemlig@y.se är inte tillåten"):
# en citerad lokaldel ("hemlig,bcc"@evil.com, även med \" inuti) eller ett
# ord med @. Ordet matchas bara från ordets början (bakåtblicken), så att
# ett långt ord utan @ läses en gång och inte en gång per tecken.
_DELIMS = r"\s<>\"',;:()\[\]"
_EMAIL_RE = re.compile(
    rf'"(?:[^"\\\r\n]|\\.)*"@[^{_DELIMS}]+'
    rf"|(?<![^{_DELIMS}])[^{_DELIMS}]+@[^{_DELIMS}]+"
)
_MASK = "<adress>"

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


def _full_error_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}" if str(error) else type(error).__name__


def _clip(text: str) -> str:
    return text if len(text) <= _MAX_ERROR_CHARS else text[:_MAX_ERROR_CHARS] + " …"


def _error_text(error: BaseException) -> str:
    return _clip(_full_error_text(error))


def record(
    settings: Any,
    action: str,
    *,
    result: str,
    error: BaseException | None = None,
    **fields: Any,
) -> None:
    """Skriv en granskningsrad. Fält med värdet None utelämnas. Kastar aldrig."""
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": current_tool.get(),
        "action": action,
    }
    entry.update({key: value for key, value in fields.items() if value is not None})
    entry["result"] = result
    full_error = _full_error_text(error) if error is not None else None
    if full_error is not None:
        entry["error"] = _clip(full_error)
    try:
        line = json.dumps(entry, ensure_ascii=False, default=str)
        stderr_line = json.dumps(_redacted(entry, full_error), ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:  # ska inte hända; operationen får inte stoppas
        logger.warning("Kunde inte skapa granskningsraden för %s: %s", action, exc)
        return
    logger.info("%s", stderr_line)
    path = getattr(settings, "audit_log", None)
    if isinstance(path, Path):
        _append(path, line)


def _address_forms(address: str) -> set[str]:
    """Formerna som en känd mottagare kan stå i en feltext: som den är, med
    lokaldelen utan citattecken och med domänen i Unicode i stället för punycode."""
    local, _, domain = address.rpartition("@")
    locals_ = {local}
    if len(local) >= 2 and local.startswith('"') and local.endswith('"'):
        locals_.add(re.sub(r"\\(.)", r"\1", local[1:-1]))
    domains = {domain}
    try:
        domains.add(domain.encode("ascii").decode("idna"))
    except UnicodeError:
        pass
    return {f"{lp}@{d}" for lp in locals_ for d in domains if lp and d}


def mask_addresses(text: str, recipients: Any = ()) -> str:
    """Feltexten med adresserna maskerade som <adress>.

    Först ersätts exakt de kända mottagarna (alla former, utan hänsyn till
    skiftläge), sedan allt som ser ut som en adress, även med citerad
    lokaldel. Anroparen kapar texten efteråt, så att en kapning aldrig
    lämnar en halv adress omaskerad.
    """
    known: set[str] = set()
    if isinstance(recipients, (list, tuple, set)):
        for address in recipients:
            if isinstance(address, str) and "@" in address:
                known |= _address_forms(address)
    if known:
        pattern = "|".join(re.escape(a) for a in sorted(known, key=len, reverse=True))
        text = re.sub(pattern, _MASK, text, flags=re.IGNORECASE)
    return _EMAIL_RE.sub(_MASK, text)


def _redacted(entry: dict[str, Any], full_error: str | None = None) -> dict[str, Any]:
    """Raden för stderr: antal mottagare i stället för adresser, maskerad feltext.

    Feltexten maskeras i sin fulla längd och kapas sist.
    """
    redacted = dict(entry)
    recipients = entry.get("recipients", ())
    if "recipients" in redacted:
        redacted["recipients"] = {"count": len(redacted["recipients"])}
    if "error" in redacted:
        source = full_error if full_error is not None else redacted["error"]
        redacted["error"] = _clip(mask_addresses(source, recipients))
    return redacted


def _append(path: Path, line: str) -> None:
    """Lägg till raden i filen: skapas 0600, aldrig via symlänk eller hård länk."""
    try:
        if not _O_NOFOLLOW and path.is_symlink():  # plattform utan O_NOFOLLOW
            raise OSError("sökvägen är en symlänk")
        fd = os.open(
            path,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | _O_NOFOLLOW | _O_NONBLOCK | _O_CLOEXEC,
            0o600,
        )
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise OSError("inte en vanlig fil")
            if st.st_nlink != 1:
                raise OSError("filen har flera hårda länkar")
            if stat.S_IMODE(st.st_mode) & 0o077:
                os.fchmod(fd, 0o600)
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError as exc:
        logger.warning("Kunde inte skriva granskningsloggen %s: %s", path, exc)

"""En liten låtsas-Bridge för flytt-, raderings- och mapptesterna (fix-flytta).

Den riktiga IMAPClient används; bara aioimaplib-anslutningen byts ut. Låtsas-
Bridgen håller reda på vilka UID:n som finns i vilken mapp och loggar varje
kommando, så att testerna kan kontrollera både vad som skickades och vad som
aldrig fick skickas (t.ex. EXPUNGE utan UID).
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient


def _ok(*lines):
    return SimpleNamespace(result="OK", lines=[*lines, b"command completed"])


def _no(text: str = "operation not allowed"):
    return SimpleNamespace(result="NO", lines=[text.encode()])


class FakeBridge:
    def __init__(self) -> None:
        # Läsbart mappnamn → UID:n i mappen
        self.mailboxes: dict[str, set[str]] = {
            "INBOX": set(), "Drafts": set(), "Sent": set(), "Starred": set(),
            "Archive": set(), "Spam": set(), "Trash": set(), "All Mail": set(),
        }
        self.selected: str | None = None
        self.commands: list[tuple] = []
        # Kommandon (versaler, t.ex. "MOVE") som Bridge ska svara NO på
        self.refuse: dict[str, str] = {}
        # Behållare som LIST visar med \Noselect, t.ex. "Folders" och "Labels"
        self.containers: set[str] = set()

        client = AsyncMock()
        client.noop.return_value = _ok()
        client.select.side_effect = self._select
        client.uid.side_effect = self._uid
        client.expunge.side_effect = self._expunge
        client.status.side_effect = self._status
        client.list.side_effect = self._list
        client.create.side_effect = self._simple("CREATE")
        client.delete.side_effect = self._simple("DELETE")
        client.rename.side_effect = self._simple("RENAME")
        client.has_capability = MagicMock(return_value=True)
        # IMAPClient återansluter om klienten inte ser inloggad ut
        client.protocol = MagicMock()
        client.protocol.state = "SELECTED"
        self.client = client

    # --- hjälpare för testerna -------------------------------------------
    def add(self, mailbox: str, uid: str) -> None:
        self.mailboxes.setdefault(mailbox, set()).add(uid)

    def names(self) -> list[str]:
        """Kommandonamnen i ordning, t.ex. ["SELECT", "UID FETCH", "UID MOVE"]."""
        return [c[0] for c in self.commands]

    def sent(self, name: str) -> list[tuple]:
        return [c for c in self.commands if c[0] == name]

    # --- IMAP --------------------------------------------------------------
    @staticmethod
    def _unquote(quoted: str) -> str:
        return quoted[1:-1] if quoted.startswith('"') else quoted

    async def _select(self, quoted: str):
        name = self._unquote(quoted)
        self.commands.append(("SELECT", name))
        if name not in self.mailboxes:
            return _no("no such mailbox")
        self.selected = name
        return _ok(f"* {len(self.mailboxes[name])} EXISTS".encode())

    async def _uid(self, command: str, *args: str):
        name = f"UID {command.upper()}"
        self.commands.append((name, *args))
        if command.upper() in self.refuse:
            return _no(self.refuse[command.upper()])
        if command.upper() == "FETCH":
            uid = args[0]
            if uid in self.mailboxes.get(self.selected, set()):
                return _ok(f"1 FETCH (UID {uid})".encode())
            # Bridge svarar OK utan data för UID:n som inte finns
            return _ok()
        return _ok()

    async def _expunge(self, *args):
        self.commands.append(("EXPUNGE", *args))
        return _ok()

    async def _status(self, quoted: str, items: str):
        name = self._unquote(quoted)
        self.commands.append(("STATUS", name, items))
        if name not in self.mailboxes:
            return _no("no such mailbox")
        n = len(self.mailboxes[name])
        return _ok(f'"{name}" (MESSAGES {n} UNSEEN 0)'.encode())

    async def _list(self, reference: str, pattern: str):
        pattern = self._unquote(pattern)
        self.commands.append(("LIST", pattern))
        if "LIST" in self.refuse:
            return _no(self.refuse["LIST"])
        # IMAP-mönster: "*" matchar allt, "%" allt utom nivåavgränsaren
        regex = re.compile("".join(
            ".*" if c == "*" else "[^/]*" if c == "%" else re.escape(c) for c in pattern
        ))
        lines = []
        for name in [*sorted(self.containers), *self.mailboxes]:
            if regex.fullmatch(name):
                attrs = "\\Noselect" if name in self.containers else "\\HasNoChildren"
                lines.append(f'({attrs}) "/" "{name}"'.encode())
        return _ok(*lines)

    def _simple(self, cmd: str):
        async def handler(*args):
            self.commands.append((cmd, *(self._unquote(a) for a in args)))
            if cmd in self.refuse:
                return _no(self.refuse[cmd])
            return _ok()
        return handler


def make_client(monkeypatch) -> tuple[IMAPClient, FakeBridge]:
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    imap = IMAPClient(Settings())
    bridge = FakeBridge()
    imap._client = bridge.client
    return imap, bridge

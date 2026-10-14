"""Låtsas-Bridge med riktiga meddelanden för utkasttesterna (feat-utkast).

Den riktiga IMAPClient används; bara aioimaplib-anslutningen byts ut. Varje
mapp håller UID → (råa bytes, flaggor), så att APPEND, UID FETCH BODY.PEEK[],
SEARCH HEADER Message-ID, UID STORE och UID EXPUNGE beter sig som mot Bridge
(Drafts: EXPUNGE raderar permanent). Alla kommandon loggas i ordning.
"""
from __future__ import annotations

import email
import email.policy
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient

_HEADER_SEARCH_RE = re.compile(r'HEADER\s+Message-ID\s+"((?:[^"\\]|\\.)*)"', re.IGNORECASE)


def _ok(*lines):
    return SimpleNamespace(result="OK", lines=[*lines])


def _no(text: str = "operation not allowed"):
    return SimpleNamespace(result="NO", lines=[text.encode()])


def _unquote(quoted: str) -> str:
    return quoted[1:-1] if quoted.startswith('"') else quoted


class FakeDraftsBridge:
    def __init__(self) -> None:
        self.mailboxes: dict[str, dict[int, dict]] = {
            name: {} for name in ("INBOX", "Drafts", "Sent", "Trash", "All Mail")
        }
        self.next_uid: dict[str, int] = {name: 1 for name in self.mailboxes}
        self.selected: str | None = None
        self.commands: list[tuple] = []
        # Kommandon (versaler, t.ex. "APPEND" eller "EXPUNGE") som ska få NO
        self.refuse: dict[str, str] = {}
        # Bridge annonserar UIDPLUS och svarar med APPENDUID; kan stängas av
        self.appenduid = True

        client = AsyncMock()
        client.noop.return_value = _ok(b"NOOP completed")
        client.select.side_effect = self._select
        client.uid.side_effect = self._uid
        client.append.side_effect = self._append
        client.search.side_effect = self._search
        client.fetch.side_effect = self._fetch
        client.has_capability = MagicMock(return_value=True)
        client.protocol = MagicMock()
        client.protocol.state = "SELECTED"
        self.client = client

    # --- hjälpare för testerna -------------------------------------------
    def add(self, mailbox: str, raw: bytes, flags: tuple[str, ...] = ()) -> str:
        uid = self.next_uid[mailbox]
        self.next_uid[mailbox] += 1
        self.mailboxes[mailbox][uid] = {"raw": raw, "flags": set(flags)}
        return str(uid)

    def messages(self, mailbox: str) -> dict[int, dict]:
        return self.mailboxes[mailbox]

    def parsed(self, mailbox: str, uid: str | int) -> email.message.EmailMessage:
        raw = self.mailboxes[mailbox][int(uid)]["raw"]
        return email.message_from_bytes(raw, policy=email.policy.default)

    def names(self) -> list[str]:
        return [c[0] for c in self.commands]

    # --- IMAP --------------------------------------------------------------
    async def _select(self, quoted: str):
        name = _unquote(quoted)
        self.commands.append(("SELECT", name))
        if name not in self.mailboxes:
            return _no("no such mailbox")
        self.selected = name
        return _ok(f"{len(self.mailboxes[name])} EXISTS".encode(), b"SELECT completed")

    async def _append(self, message_bytes, mailbox="INBOX", flags=None, date=None, timeout=None):
        name = _unquote(mailbox)
        self.commands.append(("APPEND", name, flags))
        if "APPEND" in self.refuse:
            return _no(self.refuse["APPEND"])
        if name not in self.mailboxes:
            return _no("no such mailbox")
        found = re.findall(r"\\\w+", flags or "")
        uid = self.add(name, bytes(message_bytes), tuple(found))
        if self.appenduid:
            return _ok(f"[APPENDUID 1 {uid}] APPEND completed".encode())
        return _ok(b"APPEND completed")

    def _ordered(self) -> list[int]:
        return sorted(self.mailboxes[self.selected])

    async def _search(self, *criteria, charset="utf-8"):
        command = " ".join(criteria)
        self.commands.append(("SEARCH", command))
        if "SEARCH" in self.refuse:
            return _no(self.refuse["SEARCH"])
        m = _HEADER_SEARCH_RE.search(command)
        hits = []
        if m:
            wanted = m.group(1).replace('\\"', '"').replace("\\\\", "\\")
            for seq, uid in enumerate(self._ordered(), start=1):
                msg = self.parsed(self.selected, uid)
                if (msg["Message-ID"] or "").strip() == wanted:
                    hits.append(str(seq))
        return _ok(" ".join(hits).encode(), b"SEARCH completed")

    async def _fetch(self, seqset: str, items: str):
        self.commands.append(("FETCH", seqset, items))
        ordered = self._ordered()
        lines = []
        for seq in seqset.split(","):
            uid = ordered[int(seq) - 1]
            lines.append(f"{seq} FETCH (UID {uid})".encode())
        return _ok(*lines, b"FETCH completed")

    async def _uid(self, command: str, *args: str):
        cmd = command.upper()
        self.commands.append((f"UID {cmd}", *args))
        if cmd in self.refuse:
            return _no(self.refuse[cmd])
        box = self.mailboxes[self.selected]
        if cmd == "FETCH":
            uid = int(args[0])
            if uid not in box:
                return _ok(b"FETCH completed")  # Bridge: OK utan data
            seq = self._ordered().index(uid) + 1
            if "BODY.PEEK[]" in args[1]:
                raw = box[uid]["raw"]
                return _ok(
                    f"{seq} FETCH (UID {uid} BODY[] {{{len(raw)}}}".encode(),
                    bytearray(raw),
                    b")",
                    b"FETCH completed",
                )
            return _ok(f"{seq} FETCH (UID {uid})".encode(), b"FETCH completed")
        if cmd == "STORE":
            uid, action, flags = int(args[0]), args[1], args[2]
            if uid in box:
                found = set(re.findall(r"\\\w+", flags))
                if action.startswith("+"):
                    box[uid]["flags"] |= found
                else:
                    box[uid]["flags"] -= found
            return _ok(b"STORE completed")
        if cmd == "EXPUNGE":
            uid = int(args[0])
            if uid in box and "\\Deleted" in box[uid]["flags"]:
                del box[uid]
            return _ok(b"EXPUNGE completed")
        return _ok(b"completed")


def make_imap(monkeypatch=None) -> tuple[IMAPClient, FakeDraftsBridge]:
    imap = IMAPClient(Settings(username="me@proton.me", password="pw", _env_file=None))
    bridge = FakeDraftsBridge()
    imap._client = bridge.client
    return imap, bridge

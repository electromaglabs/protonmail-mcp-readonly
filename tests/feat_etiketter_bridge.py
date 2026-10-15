"""En låtsas-Bridge med Protons etikettsemantik (feat-etiketter).

Den riktiga IMAPClient används; bara aioimaplib-anslutningen byts ut. Varje
mejl finns en gång (nyckel = Message-ID) och kan synas i flera vyer — en mapp
plus valfritt antal etiketter — med ett eget UID per vy, som hos Bridge:

- UID COPY till Labels/… lägger till etiketten; mejlet ligger kvar i källan.
- UID MOVE till en mapp flyttar; från en etikett tas etiketten bort.
- UID EXPUNGE i en etikett tar bara bort etiketten.
- \\Deleted gäller per vy, \\Seen och \\Flagged för mejlet i alla vyer.
- SEARCH HEADER Message-ID är en delsträngsmatchning, som hos Bridge.

Alla kommandon loggas, så att testerna kan kontrollera både vad som skickades
och vad som aldrig fick skickas (t.ex. EXPUNGE utan UID).
"""
from __future__ import annotations

import hashlib
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from protonmail_mcp.mailbox_names import decode_modified_utf7

WRITES = {"UID MOVE", "UID COPY", "UID STORE", "UID EXPUNGE", "EXPUNGE", "CREATE", "DELETE", "RENAME"}
_HEADER_MID_RE = re.compile(r'HEADER Message-ID "((?:[^"\\]|\\.)*)"', re.IGNORECASE)
_HEADER_PMID_RE = re.compile(r'HEADER X-Pm-Internal-Id "((?:[^"\\]|\\.)*)"', re.IGNORECASE)


def _ok(*lines):
    return SimpleNamespace(result="OK", lines=[*lines, b"command completed"])


def _no(text: str = "operation not allowed"):
    return SimpleNamespace(result="NO", lines=[text.encode()])


def _is_label(name: str) -> bool:
    return name.startswith("Labels/") or name == "Starred"


class LabelBridge:
    SYSTEM = ("INBOX", "Drafts", "Sent", "Starred", "Archive", "Spam", "Trash", "All Mail")
    # Bridge sätter X-Pm-Internal-Id (Protons mejl-id) på alla mejl. Av som
    # standard här, så att äldre tester prövar reservvägen utan rubriken.
    internal_ids = False

    def __init__(self) -> None:
        # vy → {uid: Message-ID}
        self.views: dict[str, dict[str, str]] = {name: {} for name in self.SYSTEM}
        self.next_uid: dict[str, int] = {}
        self.messages: dict[str, dict] = {}  # Message-ID → {"date", "size", "flags"}
        self.deleted: set[tuple[str, str]] = set()  # (vy, uid) med \Deleted
        self.selected: str | None = None
        self.commands: list[tuple] = []
        self.refuse: dict[str, str] = {}
        self.errors: list[str] = []
        self.result = None

        client = AsyncMock()
        client.noop.side_effect = self._noop
        client.select.side_effect = self._select
        client.list.side_effect = self._list
        client.uid.side_effect = self._uid
        client.fetch.side_effect = self._fetch
        client.search.side_effect = self._search
        client.expunge.side_effect = self._expunge
        client.protocol = MagicMock()
        client.protocol.state = "SELECTED"
        self.client = client

    # --- hjälpare för testerna -------------------------------------------
    def add_label(self, label: str) -> None:
        self.views.setdefault(label, {})

    def put(self, view: str, uid: str, message_id: str | None = None,
            date: str = "25-Mar-2025 13:31:04 +0000", size: int = 1000) -> str:
        """Lägger mejlet i vyn med givet UID. Utan Message-ID får det ett unikt."""
        message_id = message_id or f"<auto-{view}-{uid}@test>"
        self.messages.setdefault(message_id, {"date": date, "size": size, "flags": set()})
        self.views.setdefault(view, {})[uid] = message_id
        self.next_uid[view] = max(self.next_uid.get(view, 0), int(uid))
        return message_id

    def internal_id(self, key: str) -> str:
        """Protons mejl-id för mejlet: samma i alla vyer, olika för olika mejl."""
        return "pm" + hashlib.sha1(key.encode()).hexdigest()

    def shown_message_id(self, key: str) -> str:
        """Message-ID-rubriken som FETCH visar för mejlet med nyckeln key."""
        return key

    def views_of(self, message_id: str) -> list[str]:
        return [v for v, uids in self.views.items() if message_id in uids.values()]

    def sent(self, name: str) -> list[tuple]:
        return [c for c in self.commands if c[0] == name]

    def writes(self) -> list[tuple]:
        return [c for c in self.commands if c[0] in WRITES]

    # --- intern logik --------------------------------------------------------
    @staticmethod
    def _name(quoted: str) -> str:
        wire = quoted[1:-1] if quoted.startswith('"') else quoted
        return decode_modified_utf7(re.sub(r'\\(.)', r'\1', wire))

    def _sorted_uids(self, view: str) -> list[str]:
        return sorted(self.views.get(view, {}), key=int)

    def _new_uid(self, view: str) -> str:
        self.next_uid[view] = self.next_uid.get(view, 0) + 1
        return str(self.next_uid[view])

    def _attach(self, view: str, message_id: str) -> None:
        if message_id not in self.views[view].values():
            self.views[view][self._new_uid(view)] = message_id

    def _detach(self, view: str, uid: str) -> None:
        self.views[view].pop(uid, None)
        self.deleted.discard((view, uid))

    def _uid_set(self, text: str) -> list[str]:
        uids = []
        for part in text.split(","):
            if not part.isdigit():
                raise AssertionError(f"Låtsas-Bridgen stöder bara rena UID-listor, fick {text!r}")
            uids.append(part)
        return uids

    def _fetch_lines(self, seq_uid: list[tuple[int, str]], items: str, uid_after: bool) -> list:
        lines: list = []
        view = self.selected
        for seq, uid in seq_uid:
            mid = self.views[view][uid]
            msg = self.messages[mid]
            parts = []
            if not uid_after:
                parts.append(f"UID {uid}")
            if "FLAGS" in items:
                flags = set(msg["flags"])
                if (view, uid) in self.deleted:
                    flags.add("\\Deleted")
                parts.append(f"FLAGS ({' '.join(sorted(flags))})")
            if "INTERNALDATE" in items:
                parts.append(f'INTERNALDATE "{msg["date"]}"')
            if "RFC822.SIZE" in items:
                parts.append(f"RFC822.SIZE {msg['size']}")
            if "MESSAGE-ID" in items.upper():
                text = f"Message-Id: {self.shown_message_id(mid)}\r\n"
                if self.internal_ids and "X-PM-INTERNAL-ID" in items.upper():
                    text += f"X-Pm-Internal-Id: {self.internal_id(mid)}\r\n"
                literal = f"{text}\r\n".encode()
                head = " ".join(parts + [f"BODY[HEADER.FIELDS (MESSAGE-ID)] {{{len(literal)}}}"])
                lines.append(f"{seq} FETCH ({head}".encode())
                lines.append(bytearray(literal))
                lines.append(f" UID {uid})".encode() if uid_after else b")")
            else:
                if uid_after:
                    parts.append(f"UID {uid}")
                lines.append(f"{seq} FETCH ({' '.join(parts)})".encode())
        return lines

    # --- IMAP --------------------------------------------------------------
    async def _noop(self):
        return _ok()

    async def _select(self, quoted: str):
        name = self._name(quoted)
        self.commands.append(("SELECT", name))
        if name not in self.views:
            return _no("no such mailbox")
        self.selected = name
        return _ok(f"{len(self.views[name])} EXISTS".encode())

    async def _list(self, ref: str, pattern: str):
        name = self._name(pattern)
        self.commands.append(("LIST", name))
        if "LIST" in self.refuse:
            return _no(self.refuse["LIST"])
        lines = [
            f'(\\HasNoChildren) "/" "{view}"'.encode()
            for view in self.views if pattern == "*" or view == name
        ]
        return _ok(*lines)

    async def _search(self, *criteria, **_kwargs):
        text = " ".join(criteria)
        self.commands.append(("SEARCH", text))
        if "SEARCH" in self.refuse:
            return _no(self.refuse["SEARCH"])
        terms = [re.sub(r'\\(.)', r'\1', t).casefold() for t in _HEADER_MID_RE.findall(text)]
        pm_terms = [re.sub(r'\\(.)', r'\1', t).casefold() for t in _HEADER_PMID_RE.findall(text)]
        view = self.views[self.selected]
        hits = [
            str(seq) for seq, uid in enumerate(self._sorted_uids(self.selected), start=1)
            if any(t in self.shown_message_id(view[uid]).casefold() for t in terms)
            or (self.internal_ids and any(t in self.internal_id(view[uid]) for t in pm_terms))
        ]
        return _ok(" ".join(hits).encode())

    async def _fetch(self, seqset: str, items: str):
        self.commands.append(("FETCH", seqset, items))
        uids = self._sorted_uids(self.selected)
        wanted = [int(s) for s in seqset.split(",")]
        pairs = [(s, uids[s - 1]) for s in wanted if 1 <= s <= len(uids)]
        return _ok(*self._fetch_lines(pairs, items, uid_after=False))

    async def _uid(self, command: str, *args: str):
        cmd = command.upper()
        self.commands.append((f"UID {cmd}", *args))
        if cmd in self.refuse:
            return _no(self.refuse[cmd])
        view = self.selected
        uids = self._uid_set(args[0])
        present = [u for u in uids if u in self.views[view]]
        if cmd == "FETCH":
            order = self._sorted_uids(view)
            pairs = [(order.index(u) + 1, u) for u in present]
            return _ok(*self._fetch_lines(pairs, args[1], uid_after=True))
        if cmd == "STORE":
            action, flags = args[1], args[2].strip("()").split()
            for u in present:
                for flag in flags:
                    if flag == "\\Deleted":
                        (self.deleted.add if action == "+FLAGS" else self.deleted.discard)((view, u))
                    else:
                        msg_flags = self.messages[self.views[view][u]]["flags"]
                        (msg_flags.add if action == "+FLAGS" else msg_flags.discard)(flag)
            return _ok()
        if cmd in ("COPY", "MOVE"):
            target = self._name(args[1])
            if target not in self.views:
                return _no("no such mailbox")
            for u in present:
                mid = self.views[view][u]
                if not _is_label(target):
                    # Mappar är exklusiva: mejlet lämnar sin förra mapp
                    for other in list(self.views):
                        if not _is_label(other) and other != "All Mail":
                            for ou, omid in list(self.views[other].items()):
                                if omid == mid:
                                    self._detach(other, ou)
                elif cmd == "MOVE" and _is_label(view):
                    self._detach(view, u)
                self._attach(target, mid)
            return _ok()
        if cmd == "EXPUNGE":
            for u in present:
                if (view, u) in self.deleted:
                    self._detach(view, u)
            return _ok()
        raise AssertionError(f"Okänt UID-kommando i låtsas-Bridgen: {command}")

    async def _expunge(self, *args):
        self.commands.append(("EXPUNGE", *args))
        return _ok()


def make_client(monkeypatch) -> tuple[IMAPClient, LabelBridge]:
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    imap = IMAPClient(Settings())
    bridge = LabelBridge()
    imap._client = bridge.client
    return imap, bridge

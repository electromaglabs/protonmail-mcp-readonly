"""Falsk Bridge för feat-sok-testerna: SEARCH, FETCH och UID FETCH som Gluon.

Bridge (Gluon) jämför sökord mot det *okodade* meddelandet, skiftlägesoberoende:
headers med åäö står RFC 2047-kodade och textdelar är quoted-printable. Den här
fejken bygger meddelandena likadant och jämför på samma sätt, så att testerna
visar samma beteende som riktiga Bridge (verifierat live, se rapporten).
"""
from __future__ import annotations

import quopri
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

_TOKEN_RE = re.compile(r'"((?:[^"\\]|\\.)*)"|(\S+)')

_PART_STRUCTURE = {
    "text": '("text" "html" ("charset" "utf-8") NIL NIL "quoted-printable" 120 3 NIL NIL NIL NIL)',
    "attachment": (
        '("application" "pdf" ("filename" "Avtal.pdf" "name" "Avtal.pdf") "<a1>" NIL "base64" '
        '5922206 NIL ("attachment" ("filename" "Avtal.pdf")) NIL NIL)'
    ),
    "inline-bild": (
        '("image" "png" ("name" "logo.png") "<logo>" NIL "base64" 2048 NIL '
        '("inline" ("filename" "logo.png")) NIL NIL)'
    ),
}


@dataclass
class FakeMessage:
    uid: int
    headers: dict[str, str] = field(default_factory=dict)  # råa (okodade) headervärden
    body: str = ""
    flags: list[str] = field(default_factory=list)
    size: int = 1000
    content_type: str = "text/html"
    parts: list[str] = field(default_factory=lambda: ["text"])

    def raw_headers(self) -> str:
        lines = [f"{k}: {v}" for k, v in self.headers.items() if v]
        lines.append(f"Content-Type: {self.content_type}")
        return "\r\n".join(lines) + "\r\n\r\n"

    def raw_body(self) -> str:
        # Bridge skriver textdelar som quoted-printable i UTF-8
        return quopri.encodestring(self.body.encode("utf-8")).decode("ascii")

    def raw(self) -> str:
        return self.raw_headers() + self.raw_body()

    def header(self, name: str) -> str:
        for k, v in self.headers.items():
            if k.lower() == name.lower():
                return v
        if name.lower() == "content-type":
            return self.content_type
        return ""

    def bodystructure(self) -> str:
        structures = [_PART_STRUCTURE[p] for p in self.parts]
        if not self.content_type.startswith("multipart/"):
            return structures[0]
        subtype = self.content_type.split("/", 1)[1]
        return "(" + "".join(structures) + f' "{subtype}" ("boundary" "b") NIL NIL NIL)'


class FakeBridge:
    def __init__(self):
        self.boxes: dict[str, list[FakeMessage]] = {}
        self.selected: str | None = None
        self.search_commands: list[str] = []

    # --- uppbyggnad -------------------------------------------------------
    def add(self, mailbox: str, message: FakeMessage) -> FakeMessage:
        self.boxes.setdefault(mailbox, []).append(message)
        return message

    def client(self) -> AsyncMock:
        m = AsyncMock()
        m.protocol = MagicMock()
        m.protocol.state = "SELECTED"
        m.login.return_value = SimpleNamespace(result="OK", lines=[])
        m.noop.return_value = SimpleNamespace(result="OK", lines=[])
        m.select.side_effect = self._select
        m.search.side_effect = self._search
        m.fetch.side_effect = self._fetch
        m.uid.side_effect = self._uid
        return m

    # --- IMAP ---------------------------------------------------------------
    async def _select(self, quoted: str, *args, **kwargs):
        name = quoted.strip('"').replace('\\"', '"').replace("\\\\", "\\")
        if name not in self.boxes:
            return SimpleNamespace(result="NO", lines=[b"no such mailbox"])
        self.selected = name
        return SimpleNamespace(result="OK", lines=[f"{len(self.boxes[name])} EXISTS".encode()])

    def _messages(self) -> list[FakeMessage]:
        return self.boxes[self.selected]

    async def _search(self, criteria: str, *args, **kwargs):
        self.search_commands.append(criteria)
        found = list(_TOKEN_RE.finditer(criteria))
        tokens = [m.group(1) if m.group(1) is not None else m.group(2) for m in found]
        quoted = {i for i, m in enumerate(found) if m.group(1) is not None}
        hits = []
        for seq, msg in enumerate(self._messages(), start=1):
            pos, ok = 0, True
            while pos < len(tokens):
                pos, match = _evaluate(tokens, quoted, pos, msg)
                ok = ok and match
            if ok:
                hits.append(str(seq))
        return SimpleNamespace(result="OK", lines=[" ".join(hits).encode(), b"SEARCH completed"])

    async def _fetch(self, message_set: str, items: str, **kwargs):
        wanted = {int(s) for s in message_set.split(",")}
        lines: list = []
        for seq, msg in enumerate(self._messages(), start=1):
            if seq in wanted:
                lines += _fetch_lines(seq, msg, items)
        return SimpleNamespace(result="OK", lines=[*lines, b"FETCH completed"])

    async def _uid(self, command: str, *args):
        if command.lower() != "fetch":
            raise AssertionError(f"FakeBridge stöder bara UID FETCH (fick {command})")
        uid_set, items = args
        wanted = {int(s) for s in uid_set.split(",")}
        lines: list = []
        for seq, msg in enumerate(self._messages(), start=1):
            if msg.uid in wanted:
                lines += _fetch_lines(seq, msg, items)
        return SimpleNamespace(result="OK", lines=[*lines, b"UID FETCH completed"])


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def _evaluate(tokens: list[str], quoted: set[int], pos: int, msg: FakeMessage) -> tuple[int, bool]:
    key = tokens[pos].upper() if pos not in quoted else tokens[pos]
    pos += 1
    if key == "ALL":
        return pos, True
    if key in ("SEEN", "UNSEEN"):
        return pos, ("\\Seen" in msg.flags) == (key == "SEEN")
    if key in ("FLAGGED", "UNFLAGGED"):
        return pos, ("\\Flagged" in msg.flags) == (key == "FLAGGED")
    if key in ("ANSWERED", "UNANSWERED"):
        return pos, ("\\Answered" in msg.flags) == (key == "ANSWERED")
    if key in ("SINCE", "BEFORE"):
        return pos + 1, True  # datum testas inte här
    if key == "LARGER":
        return pos + 1, msg.size > int(tokens[pos])
    if key == "SMALLER":
        return pos + 1, msg.size < int(tokens[pos])
    if key in ("FROM", "TO", "CC", "SUBJECT"):
        return pos + 1, _contains(msg.header(key), _unescape(tokens[pos]))
    if key == "HEADER":
        return pos + 2, _contains(msg.header(tokens[pos]), _unescape(tokens[pos + 1]))
    if key == "TEXT":
        return pos + 1, _contains(msg.raw(), _unescape(tokens[pos]))
    if key == "BODY":
        return pos + 1, _contains(msg.raw_body(), _unescape(tokens[pos]))
    if key == "NOT":
        pos, match = _evaluate(tokens, quoted, pos, msg)
        return pos, not match
    if key == "OR":
        pos, first = _evaluate(tokens, quoted, pos, msg)
        pos, second = _evaluate(tokens, quoted, pos, msg)
        return pos, first or second
    raise AssertionError(f"FakeBridge känner inte igen söknyckeln {key!r}")


def _unescape(value: str) -> str:
    return re.sub(r"\\(.)", r"\1", value)


_HEADER_FIELDS_RE = re.compile(r"HEADER\.FIELDS \(([^)]*)\)", re.IGNORECASE)


def _fetch_lines(seq: int, msg: FakeMessage, items: str) -> list:
    flags = " ".join(msg.flags)
    fields = _HEADER_FIELDS_RE.search(items)
    if fields:
        names = fields.group(1).split()
        data = "".join(
            f"{n.title()}: {msg.header(n)}\r\n" for n in names if msg.header(n)
        ) + "\r\n"
        raw = data.encode("utf-8")
        return [
            f"{seq} FETCH (UID {msg.uid} FLAGS ({flags}) BODY[HEADER.FIELDS ({fields.group(1)})] {{{len(raw)}}}".encode(),
            bytearray(raw),
            b")",
        ]
    if "BODYSTRUCTURE" in items.upper():
        return [f"{seq} FETCH (UID {msg.uid} BODYSTRUCTURE {msg.bodystructure()})".encode()]
    return [f"{seq} FETCH (UID {msg.uid})".encode()]

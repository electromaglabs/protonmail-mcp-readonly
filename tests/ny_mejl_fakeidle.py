"""En låtsas-Bridge över TCP med IMAP IDLE (RFC 2177), för ny-mejl-testerna.

Startas på en slumpport på 127.0.0.1 (testspärren i tests/conftest.py stoppar
1143/1026). Stöder det bevakningen och verktygen behöver: CAPABILITY, LOGIN,
SELECT (EXISTS, UIDVALIDITY, UIDNEXT), LIST, STATUS, NOOP, LOGOUT, IDLE/DONE,
UID SEARCH UID n:*, FETCH och UID FETCH av UID, FLAGS och rubriker. Som
Bridge svarar UID SEARCH med en UID-mängd ``NO no such message`` i en tom mapp.

Allt som tas emot sparas i ``commands`` som (anslutningsnummer, rad), så att
testerna kan se t.ex. hur många IDLE som skickats på en anslutning och att
inget hämtades utan BODY.PEEK. En FETCH av BODY[...] utan PEEK sätter \\Seen,
som hos en riktig server.

Som Bridge (gluon, internal/session/handle.go) får en anslutning som inte är
i IDLE sina köade uppdateringar (``* n EXISTS``) i svaret på NÄSTA kommando i
den valda mappen, före taggat OK — och aldrig igen. ``during`` låter ett test
leverera ett mejl mitt i ett visst kommando (efter att svaret räknats fram),
så att EXISTS hamnar i just det svaret.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field


@dataclass
class FakeMessage:
    uid: int
    subject: str = "Hej"
    sender: str = "anna@example.com"
    flags: set[str] = field(default_factory=set)

    def header_block(self) -> bytes:
        return (
            f"Date: Thu, 15 Oct 2026 09:00:00 +0200\r\n"
            f"From: {self.sender}\r\n"
            f"To: me@proton.me\r\n"
            f"Subject: {self.subject}\r\n"
            f"Message-ID: <{self.uid}@example.com>\r\n\r\n"
        ).encode()


@dataclass
class FakeBox:
    uidvalidity: int = 1
    uidnext: int = 1
    messages: list[FakeMessage] = field(default_factory=list)


class _Conn:
    def __init__(self, number: int, writer: asyncio.StreamWriter) -> None:
        self.number = number
        self.writer = writer
        self.selected: str | None = None
        self.idle_tag: str | None = None
        # Ett mejl har kommit sedan förra svaret (Bridge köar uppdateringen)
        self.pending_exists = False


_QUOTED_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"')


def _first_arg(rest: str) -> tuple[str, str]:
    """Första argumentet (citerat eller atom) och resten av raden."""
    m = _QUOTED_RE.match(rest)
    if m:
        return re.sub(r"\\(.)", r"\1", m.group(1)), rest[m.end():].lstrip()
    value, _, tail = rest.partition(" ")
    return value, tail


class FakeIdleBridge:
    def __init__(self, *, idle: bool = True) -> None:
        self.idle_supported = idle
        # None: IDLE fungerar. "no": IDLE nekas med NO. "close": anslutningen
        # stängs direkt efter "+ idling".
        self.idle_mode: str | None = None
        self.boxes: dict[str, FakeBox] = {}
        self.commands: list[tuple[int, str]] = []
        self.connections_total = 0
        self.port: int | None = None
        self._conns: dict[int, _Conn] = {}
        self._server: asyncio.AbstractServer | None = None
        self._handlers: set[asyncio.Task] = set()
        # Engångskrokar (kommando, åtgärd) som körs mitt i nästa sådant kommando
        self._during: list[tuple[str, object]] = []

    # --- Testernas styrning ------------------------------------------------

    def add_box(self, name: str, uids: list[int] = (), uidvalidity: int = 1) -> FakeBox:
        box = FakeBox(uidvalidity=uidvalidity)
        for uid in uids:
            box.messages.append(FakeMessage(uid=uid, subject=f"Mejl {uid}"))
        box.uidnext = (max(uids) + 1) if uids else 1
        self.boxes[name] = box
        return box

    def deliver(self, mailbox: str, subject: str = "Nytt", sender: str = "anna@example.com",
                uid: int | None = None) -> int:
        """Ett nytt mejl kommer; IDLE-anslutningar som valt mappen får EXISTS."""
        box = self.boxes[mailbox]
        uid = uid if uid is not None else box.uidnext
        box.messages.append(FakeMessage(uid=uid, subject=subject, sender=sender))
        box.uidnext = max(box.uidnext, uid + 1)
        for conn in list(self._conns.values()):
            if conn.selected != mailbox:
                continue
            if conn.idle_tag is not None:
                self._write(conn, f"* {len(box.messages)} EXISTS\r\n* 1 RECENT\r\n")
            else:
                conn.pending_exists = True  # skickas i svaret på nästa kommando
        return uid

    def remove(self, mailbox: str, uid: int) -> None:
        """Mejlet försvinner ur mappen (t.ex. ett Proton-filter flyttar det)."""
        box = self.boxes[mailbox]
        box.messages = [m for m in box.messages if m.uid != uid]

    def during(self, command: str, action) -> None:
        """Kör action() en gång mitt i nästa kommando command (t.ex. "UID FETCH",
        "UID SEARCH" eller "DONE"), efter att svaret räknats fram men före taggat OK."""
        self._during.append((command.upper(), action))

    def _run_hooks(self, command: str) -> None:
        for hook in list(self._during):
            if hook[0] == command:
                self._during.remove(hook)
                hook[1]()

    def _flush(self, conn: _Conn) -> str:
        """Köade uppdateringar för den valda mappen (som gluons flush)."""
        if not conn.pending_exists or conn.selected not in self.boxes:
            return ""
        conn.pending_exists = False
        return f"* {len(self.boxes[conn.selected].messages)} EXISTS\r\n"

    def renumber(self, mailbox: str, uidvalidity: int, uids: list[int]) -> None:
        """Bridge byter UIDVALIDITY (t.ex. efter omsynkning) och numrerar om mejlen."""
        box = self.boxes[mailbox]
        for msg, uid in zip(box.messages, uids):
            msg.uid = uid
        box.messages = box.messages[:len(uids)]
        box.uidvalidity = uidvalidity
        box.uidnext = max(uids) + 1 if uids else 1

    async def drop_all(self) -> None:
        """Bridge startas om: alla anslutningar bryts."""
        for conn in list(self._conns.values()):
            conn.writer.close()
        await asyncio.sleep(0.05)

    def idle_count(self, conn: int | None = None) -> int:
        return sum(1 for n, line in self.commands if line.split(" ")[1:2] == ["IDLE"]
                   and (conn is None or n == conn))

    def fetch_lines(self) -> list[str]:
        return [line for _, line in self.commands if " FETCH " in f" {line.upper()} "]

    @property
    def open_connections(self) -> int:
        return len(self._conns)

    # --- Server -------------------------------------------------------------

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            for conn in list(self._conns.values()):
                conn.writer.close()
            for task in list(self._handlers):
                task.cancel()
            await asyncio.gather(*self._handlers, return_exceptions=True)
            await self._server.wait_closed()
            self._server = None

    def _write(self, conn: _Conn, data: str | bytes) -> None:
        if not conn.writer.is_closing():
            conn.writer.write(data.encode() if isinstance(data, str) else data)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self._handlers.add(task)
        self.connections_total += 1
        conn = _Conn(self.connections_total, writer)
        self._conns[conn.number] = conn
        caps = "IMAP4rev1 MOVE UIDPLUS" + (" IDLE" if self.idle_supported else "")
        self._write(conn, f"* OK [CAPABILITY {caps}] fake bridge\r\n")
        try:
            while line := await reader.readline():
                text = line.decode().rstrip("\r\n")
                self.commands.append((conn.number, text))
                if self._dispatch(conn, text, caps) == "logout":
                    break
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self._conns.pop(conn.number, None)
            writer.close()
            self._handlers.discard(task)

    def _dispatch(self, conn: _Conn, text: str, caps: str) -> str | None:
        if conn.idle_tag is not None:
            if text.upper() == "DONE":
                self._run_hooks("DONE")  # mejl som kommer mellan DONE och OK
                self._write(conn, f"{conn.idle_tag} OK IDLE terminated\r\n")
                conn.idle_tag = None
            return None
        tag, _, rest = text.partition(" ")
        cmd, _, args = rest.partition(" ")
        cmd = cmd.upper()
        if cmd == "UID":
            sub, _, args = args.partition(" ")
            cmd = f"UID {sub.upper()}"
        out: list[str | bytes] = []
        result = "OK"
        if cmd == "CAPABILITY":
            out.append(f"* CAPABILITY {caps}\r\n")
        elif cmd in ("LOGIN", "NOOP"):
            pass
        elif cmd == "LOGOUT":
            out.append("* BYE\r\n")
        elif cmd == "SELECT":
            name, _ = _first_arg(args)
            box = self.boxes.get(name)
            if box is None:
                result = "NO"
            else:
                conn.selected = name
                conn.pending_exists = False
                out += [
                    "* FLAGS (\\Seen \\Flagged \\Deleted \\Draft)\r\n",
                    f"* {len(box.messages)} EXISTS\r\n",
                    "* 0 RECENT\r\n",
                    f"* OK [UIDVALIDITY {box.uidvalidity}] UIDs valid\r\n",
                    f"* OK [UIDNEXT {box.uidnext}] Predicted next UID\r\n",
                ]
        elif cmd == "LIST":
            _, tail = _first_arg(args)
            name, _ = _first_arg(tail)
            if name in self.boxes:
                out.append(f'* LIST () "/" "{name}"\r\n')
        elif cmd == "STATUS":
            name, _ = _first_arg(args)
            box = self.boxes.get(name)
            if box is None:
                result = "NO"
            else:
                out.append(f'* STATUS "{name}" (MESSAGES {len(box.messages)} '
                           f"UIDNEXT {box.uidnext} UIDVALIDITY {box.uidvalidity})\r\n")
        elif cmd == "IDLE":
            if not self.idle_supported:
                result = "BAD"
            elif self.idle_mode == "no":
                result = "NO"
            elif self.idle_mode == "close":
                self._write(conn, "+ idling\r\n")
                conn.writer.close()
                return None
            else:
                conn.idle_tag = tag
                self._write(conn, "+ idling\r\n" + self._flush(conn))
                return None
        elif cmd == "UID SEARCH":
            box = self.boxes[conn.selected]
            words = args.split()
            uid_set = words[words.index("UID") + 1] if "UID" in words else "1:*"
            if "UID" in words and not box.messages:
                # Som Bridge: en UID-mängd i en tom mapp ger NO, inte ett tomt svar
                result = "NO"
            else:
                hits = self._select_uids(box, uid_set)
                out.append("* SEARCH" + "".join(f" {m.uid}" for m in hits) + "\r\n")
        elif cmd in ("FETCH", "UID FETCH"):
            box = self.boxes[conn.selected]
            message_set, _, items = args.partition(" ")
            if cmd == "UID FETCH":
                hits = self._select_uids(box, message_set)
            else:
                hits = self._select_seqs(box, message_set)
            for msg in hits:
                seq = box.messages.index(msg) + 1
                upper = items.upper()
                if "BODY[" in upper and "BODY.PEEK[" not in upper:
                    msg.flags.add("\\Seen")
                flags = " ".join(sorted(msg.flags))
                if "HEADER" in upper:
                    hdr = msg.header_block()
                    out.append(
                        f"* {seq} FETCH (UID {msg.uid} FLAGS ({flags}) "
                        f"BODY[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)] {{{len(hdr)}}}\r\n".encode()
                        + hdr + b")\r\n"
                    )
                else:
                    out.append(f"* {seq} FETCH (UID {msg.uid} FLAGS ({flags}))\r\n")
        else:
            result = "BAD"
        self._run_hooks(cmd)
        out.append(self._flush(conn))
        if result == "NO" and cmd == "UID SEARCH":
            out.append(f"{tag} NO no such message\r\n")
        else:
            out.append(f"{tag} {result} {cmd} completed\r\n")
        self._write(conn, b"".join(o if isinstance(o, bytes) else o.encode() for o in out))
        return "logout" if cmd == "LOGOUT" else None

    @staticmethod
    def _select_uids(box: FakeBox, uid_set: str) -> list[FakeMessage]:
        """Som en riktig server: "n:*" ger alltid minst det sista mejlet (RFC 3501)."""
        if not box.messages:
            return []
        return FakeIdleBridge._in_set(box.messages, uid_set, max(m.uid for m in box.messages),
                                      lambda i, m: m.uid)

    @staticmethod
    def _select_seqs(box: FakeBox, seq_set: str) -> list[FakeMessage]:
        return FakeIdleBridge._in_set(box.messages, seq_set, len(box.messages), lambda i, m: i)

    @staticmethod
    def _in_set(messages, message_set: str, top: int, number) -> list[FakeMessage]:
        """Mejlen vars nummer ligger i mängden (intervall jämförs, byggs inte upp)."""
        ranges = []
        for part in message_set.split(","):
            lo, _, hi = part.partition(":")
            lo_n = top if lo == "*" else int(lo)
            hi_n = lo_n if not hi else (top if hi == "*" else int(hi))
            ranges.append(sorted((lo_n, hi_n)))
        return [m for i, m in enumerate(messages, 1)
                if any(lo <= number(i, m) <= hi for lo, hi in ranges)]

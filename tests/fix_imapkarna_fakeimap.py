"""Fejk-IMAP-server som beter sig som ProtonMail Bridge i de avseenden
anslutningstesterna behöver.

Bridge följer inte RFC 3501 §6.3.1: ett misslyckat SELECT lämnar den förra
mappen vald. Servern här gör likadant, så att testerna kan visa vad som händer
när klienten inte kontrollerar SELECT-svaret.
"""
import asyncio
import re

_HEADER_TMPL = "Subject: {subject}\r\nFrom: avsandare@example.com\r\n\r\n"


class FakeBridge:
    def __init__(self) -> None:
        # mapp -> {uid: {"subject": str, "flags": set[str]}}
        self.mailboxes: dict[str, dict[int, dict]] = {}
        self.login_reply = "OK"          # "OK" | "NO"
        self.login_delay = 0.0           # sekunder innan LOGIN besvaras
        self.search_reply = "OK"         # "OK" | "BAD"
        self.hang: set[str] = set()      # kommandon som aldrig besvaras, t.ex. {"UID COPY"}
        self.total_connections = 0
        self.open_connections = 0
        self.stores: list[tuple[str | None, str, str]] = []  # (vald mapp, uid, flaggor)
        # Alla skrivkommandon (UID STORE/COPY/MOVE/EXPUNGE, EXPUNGE): (vald mapp, kommandorad)
        self.writes: list[tuple[str | None, str]] = []
        self.port: int | None = None
        self._server: asyncio.AbstractServer | None = None
        self._writers: set[asyncio.StreamWriter] = set()

    def add_mailbox(self, name: str, subjects: list[str] | None = None) -> None:
        self.mailboxes[name] = {
            uid: {"subject": s, "flags": set()} for uid, s in enumerate(subjects or [], start=1)
        }

    async def start(self, port: int = 0) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            self.drop_connections()
            await self._server.wait_closed()
            self._server = None

    def drop_connections(self) -> None:
        """Stänger alla öppna anslutningar, som när Bridge startas om."""
        for w in list(self._writers):
            w.close()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.total_connections += 1
        self.open_connections += 1
        self._writers.add(writer)
        state = {"selected": None}
        try:
            writer.write(b"* OK [CAPABILITY IMAP4rev1 IDLE MOVE UIDPLUS ID] Fake Bridge ready\r\n")
            await writer.drain()
            while True:
                line = await reader.readline()
                if not line:
                    break
                tag, _, rest = line.decode().rstrip("\r\n").partition(" ")
                if rest.upper().startswith("LOGIN") and self.login_delay:
                    await asyncio.sleep(self.login_delay)
                for out in self._reply(tag, rest, state):
                    writer.write(out.encode() if isinstance(out, str) else out)
                await writer.drain()
                if rest.upper().startswith("LOGOUT"):
                    break
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self.open_connections -= 1
            self._writers.discard(writer)
            writer.close()

    def _reply(self, tag: str, rest: str, state: dict) -> list:
        words = rest.split(" ")
        cmd = words[0].upper()
        key = f"{cmd} {words[1].upper()}" if cmd == "UID" and len(words) > 1 else cmd
        if key in ("UID STORE", "UID COPY", "UID MOVE", "UID EXPUNGE", "EXPUNGE"):
            self.writes.append((state["selected"], rest))
        if key in self.hang:
            return []

        if cmd == "CAPABILITY":
            return ["* CAPABILITY IMAP4rev1 IDLE MOVE UIDPLUS ID\r\n", f"{tag} OK done\r\n"]
        if cmd == "LOGIN":
            if self.login_reply == "OK":
                return [f"{tag} OK [CAPABILITY IMAP4rev1 IDLE MOVE UIDPLUS ID] logged in\r\n"]
            return [f"{tag} NO [AUTHENTICATIONFAILED] no such user\r\n"]
        if cmd in ("NOOP", "CHECK"):
            return [f"{tag} OK noop\r\n"]
        if cmd == "LOGOUT":
            return ["* BYE\r\n", f"{tag} OK bye\r\n"]
        if cmd == "LIST":
            return [f'* LIST (\\HasNoChildren) "/" "{n}"\r\n' for n in self.mailboxes] + [f"{tag} OK list\r\n"]
        if cmd == "SELECT":
            name = _arg_mailbox(rest)
            if name not in self.mailboxes:
                # Som Bridge: den förra mappen förblir vald
                return [f"{tag} NO no such mailbox\r\n"]
            state["selected"] = name
            return [f"* {len(self.mailboxes[name])} EXISTS\r\n", f"{tag} OK [READ-WRITE] select\r\n"]
        if cmd == "STATUS":
            name = _arg_mailbox(rest)
            if name not in self.mailboxes:
                return [f"{tag} NO no such mailbox\r\n"]
            msgs = self.mailboxes[name]
            unseen = sum(1 for m in msgs.values() if "\\Seen" not in m["flags"])
            return [f'* STATUS "{name}" (MESSAGES {len(msgs)} UNSEEN {unseen})\r\n', f"{tag} OK status\r\n"]

        selected = state["selected"]
        if selected is None:
            return [f"{tag} BAD no mailbox selected\r\n"]
        msgs = self.mailboxes[selected]
        uids = sorted(msgs)

        if cmd == "SEARCH":
            if self.search_reply != "OK":
                return [f"{tag} {self.search_reply} invalid search criteria\r\n"]
            return ["* SEARCH " + " ".join(str(i) for i in range(1, len(uids) + 1)) + "\r\n", f"{tag} OK search\r\n"]
        if cmd == "FETCH":
            out = []
            for seq in _expand_set(words[1], len(uids)):
                out.append(_fetch_line(seq, uids[seq - 1], msgs[uids[seq - 1]]))
            return out + [f"{tag} OK fetch\r\n"]
        if cmd == "EXPUNGE":
            return self._expunge(tag, selected)
        if cmd == "UID":
            sub = words[1].upper()
            uid = int(words[2])
            if sub == "FETCH":
                out = [] if uid not in msgs else [_fetch_line(uids.index(uid) + 1, uid, msgs[uid])]
                return out + [f"{tag} OK fetch\r\n"]
            if sub == "STORE":
                flags = rest.split(" ", 4)[4]
                self.stores.append((selected, str(uid), flags))
                if uid in msgs:
                    names = set(flags.strip("()").split())
                    if words[3].startswith("+"):
                        msgs[uid]["flags"] |= names
                    else:
                        msgs[uid]["flags"] -= names
                return [f"{tag} OK store\r\n"]
            if sub == "COPY":
                target = _arg_mailbox(rest.split(" ", 3)[3])
                if target not in self.mailboxes or uid not in msgs:
                    return [f"{tag} NO copy failed\r\n"]
                dest = self.mailboxes[target]
                dest[max(dest, default=0) + 1] = {"subject": msgs[uid]["subject"], "flags": set()}
                return [f"{tag} OK copy\r\n"]
            if sub == "MOVE":
                target = _arg_mailbox(rest.split(" ", 3)[3])
                if target not in self.mailboxes or uid not in msgs:
                    return [f"{tag} NO move failed\r\n"]
                dest = self.mailboxes[target]
                dest[max(dest, default=0) + 1] = {"subject": msgs[uid]["subject"], "flags": set()}
                del msgs[uid]
                return [f"{tag} OK move\r\n"]
            if sub == "EXPUNGE":
                return self._expunge(tag, selected)
        return [f"{tag} BAD unknown command\r\n"]

    def _expunge(self, tag: str, selected: str) -> list:
        msgs = self.mailboxes[selected]
        out = []
        for seq, uid in reversed(list(enumerate(sorted(msgs), start=1))):
            if "\\Deleted" in msgs[uid]["flags"]:
                del msgs[uid]
                out.append(f"* {seq} EXPUNGE\r\n")
        return out + [f"{tag} OK expunge\r\n"]


def _arg_mailbox(rest: str) -> str:
    m = re.search(r'"([^"]*)"', rest)
    return m.group(1) if m else rest.split(" ")[1]


def _expand_set(spec: str, count: int) -> list[int]:
    seqs: list[int] = []
    for part in spec.split(","):
        if ":" in part:
            a, b = part.split(":")
            seqs.extend(range(int(a), int(b) + 1))
        else:
            seqs.append(int(part))
    return [s for s in seqs if 1 <= s <= count]


def _fetch_line(seq: int, uid: int, msg: dict) -> bytes:
    hdr = _HEADER_TMPL.format(subject=msg["subject"]).encode()
    flags = " ".join(sorted(msg["flags"]))
    return (
        f"* {seq} FETCH (UID {uid} FLAGS ({flags}) BODY[HEADER] {{{len(hdr)}}}\r\n".encode()
        + hdr + b")\r\n"
    )

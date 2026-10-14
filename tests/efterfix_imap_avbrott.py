"""En minimal IMAP-server över TCP som stänger anslutningen på beställning.

Används för att visa vad som händer när Bridge startas om mitt i ett anrop:
efter ett visst kommandos svar ("after") eller i stället för svaret ("instead").
Bara den första anslutningen bryts; nästa anslutning beter sig normalt.
"""
import asyncio


class DroppingBridge:
    def __init__(self, command: str, when: str = "after") -> None:
        self.command = command          # t.ex. "SEARCH" eller "UID STORE"
        self.when = when                # "after" | "instead"
        self.connections = 0
        self.port: int | None = None
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader, writer) -> None:
        self.connections += 1
        drop = self.connections == 1
        writer.write(b"* OK [CAPABILITY IMAP4rev1 MOVE UIDPLUS] fake\r\n")
        await writer.drain()
        try:
            while line := await reader.readline():
                tag, _, rest = line.decode().rstrip("\r\n").partition(" ")
                words = rest.split(" ")
                cmd = words[0].upper()
                if cmd == "UID":
                    cmd = f"UID {words[1].upper()}"
                if drop and cmd == self.command and self.when == "instead":
                    break
                out = []
                if cmd == "CAPABILITY":
                    out.append("* CAPABILITY IMAP4rev1 MOVE UIDPLUS\r\n")
                elif cmd == "SELECT":
                    out += ["* 3 EXISTS\r\n"]
                elif cmd == "SEARCH":
                    out.append("* SEARCH 1 2 3\r\n")
                elif cmd == "FETCH":
                    hdr = b"Subject: Hej\r\n\r\n"
                    for seq in (1, 2, 3):
                        out.append(f"* {seq} FETCH (UID {seq} FLAGS () BODY[HEADER] {{{len(hdr)}}}\r\n".encode()
                                   + hdr + b")\r\n")
                elif cmd == "UID FETCH":
                    out.append(f"* 1 FETCH (UID {words[2]})\r\n")
                out.append(f"{tag} OK {cmd} completed\r\n")
                writer.write(b"".join(o if isinstance(o, bytes) else o.encode() for o in out))
                await writer.drain()
                if drop and cmd == self.command:
                    break
                if cmd == "LOGOUT":
                    break
        except ConnectionResetError:
            pass
        finally:
            writer.close()

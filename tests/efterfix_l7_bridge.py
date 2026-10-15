"""Låtsas-Bridge för efterfix-l7: flytt till Trash av ett mejl som redan ligger där.

Bygger på LabelBridge (tests/feat_etiketter_bridge.py) och efterliknar det
livetestet visade (fix-efterfix-live.md, L2/L7):

- Ett mejl till sig själv är ETT Proton-mejl med både Inbox och Sent; det
  syns i båda vyerna med var sitt UID (läggs in med ``put`` i båda vyerna).
- Bridge hämtar händelser från Proton var 20:e–40:e sekund. När mejlet flyttas
  ur en vy till Trash/Drafts försvinner det bara ur källvyn; övriga mappvyer
  (t.ex. Sent) visar det kvar tills nästa synk, som aldrig kommer här.
- gluon: UID COPY/MOVE till Trash eller Drafts av ett mejl som redan ligger där
  tar först bort det därifrån, och Proton-anropet som ska lägga dit det igen
  får "Message does not exist" (Code=2501). Bridge svarar NO, men mejlet är då
  raderat permanent — borta ur alla vyer, även All Mail.
"""
from __future__ import annotations

import re

from tests.feat_etiketter_bridge import LabelBridge, _is_label, _no, _ok, make_client as _make_client

CODE_2501 = "labeling messages: Message does not exist (Code=2501, Status=0)"
_READD = ("Trash", "Drafts")


class GluonBridge(LabelBridge):
    def __init__(self) -> None:
        super().__init__()
        self.no_message_id: set[str] = set()  # nycklar för mejl utan Message-ID-rubrik
        self.permanently_deleted: set[str] = set()

    def put_twin(self, view: str, uid: str, message_id: str, size: int) -> str:
        """Ett ANNAT mejl med samma Message-ID-rubrik (men annan storlek)."""
        key = f"{message_id}#tvilling-{view}-{uid}"
        return self.put(view, uid, key, size=size)

    def put_without_message_id(self, view: str, uid: str) -> str:
        key = self.put(view, uid)
        self.no_message_id.add(key)
        return key

    def _remove_everywhere(self, message_id: str) -> None:
        for view, uids in self.views.items():
            for uid, mid in list(uids.items()):
                if mid == message_id:
                    self._detach(view, uid)
        self.permanently_deleted.add(message_id)

    def _fetch_lines(self, seq_uid, items, uid_after):
        out = list(super()._fetch_lines(seq_uid, items, uid_after))
        for i, line in enumerate(out):
            if not isinstance(line, bytearray):
                continue
            key = line.decode().removeprefix("Message-Id: ").strip()
            if key in self.no_message_id:
                literal = b"\r\n"
            elif "#tvilling-" in key:
                literal = f"Message-Id: {key.split('#')[0]}\r\n\r\n".encode()
            else:
                continue
            out[i] = bytearray(literal)
            out[i - 1] = re.sub(rb"\{\d+\}$", b"{%d}" % len(literal), bytes(out[i - 1]))
        return out

    async def _uid(self, command: str, *args: str):
        cmd = command.upper()
        if cmd in ("COPY", "MOVE") and cmd not in self.refuse:
            target = self._name(args[1])
            view = self.selected
            if target in self.views and not _is_label(target) and not _is_label(view):
                self.commands.append((f"UID {cmd}", *args))
                present = [u for u in self._uid_set(args[0]) if u in self.views[view]]
                for u in present:
                    mid = self.views[view][u]
                    if target in _READD and mid in self.views[target].values():
                        self._remove_everywhere(mid)
                        return _no(CODE_2501)
                    if cmd == "MOVE":
                        # Bara källvyn uppdateras direkt; övriga vyer släpar
                        self._detach(view, u)
                    self._attach(target, mid)
                return _ok()
        return await super()._uid(command, *args)


def make_client(monkeypatch):
    imap, _ = _make_client(monkeypatch)
    bridge = GluonBridge()
    imap._client = bridge.client
    return imap, bridge

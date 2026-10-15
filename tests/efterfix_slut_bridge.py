"""Låtsas-Bridge för efterfix-slut: Protons mejl-id och mejl som inte går att skilja åt.

Bygger på LiveBridge (tests/efterfix_live_bridge.py) och lägger till:

- X-Pm-Internal-Id i FETCH-svaren (Protons eget mejl-id, samma i alla vyer;
  verifierat live 2026-10-15 i INBOX, Sent, Trash, Spam och All Mail), och
  SEARCH HEADER X-Pm-Internal-Id (fungerar live).
- ``put_twin``: ett ANNAT Proton-mejl med samma Message-ID, tid och storlek.
  Sådana par finns live (två i Trash). Nyckeln är "<id>#tvilling-N", men
  Message-Id-rubriken visar "<id>".
- gluon: UID COPY/MOVE till Trash eller Drafts av ett mejl som redan ligger
  där raderar det permanent och ger NO med Code=2501 (som GluonBridge).
"""
from __future__ import annotations

from tests.efterfix_live_bridge import CODE_2501, LiveBridge
from tests.feat_etiketter_bridge import _is_label, _no, make_client as _make_client

_READD = ("Trash", "Drafts")


class SlutBridge(LiveBridge):
    internal_ids = True

    def __init__(self) -> None:
        super().__init__()
        self._twins = 0

    def put_twin(self, view: str, uid: str, message_id: str, *, all_mail_uid: str | None = None,
                 flags: tuple[str, ...] = ()) -> str:
        """Ett annat mejl med samma Message-ID, tid och storlek som message_id. Returnerar nyckeln."""
        self._twins += 1
        key = f"{message_id}#tvilling-{self._twins}"
        self.put_mail(view, uid, key, all_mail_uid=all_mail_uid, flags=flags)
        return key

    def shown_message_id(self, key: str) -> str:
        return key.split("#", 1)[0]

    async def _uid(self, command: str, *args: str):
        cmd = command.upper()
        if cmd in ("COPY", "MOVE") and cmd not in self.refuse:
            target, view = self._name(args[1]), self.selected
            if target in _READD and not _is_label(view):
                present = [u for u in self._uid_set(args[0]) if u in self.views[view]]
                if any(self.views[view][u] in self.views[target].values() for u in present):
                    self.commands.append((f"UID {cmd}", *args))
                    for u in present:
                        mid = self.views[view][u]
                        if mid in self.views[target].values():
                            self._remove_everywhere(mid)
                    return _no(CODE_2501.replace("unlabel", "label"))
        return await super()._uid(command, *args)


def make_client(monkeypatch):
    imap, _ = _make_client(monkeypatch)
    bridge = SlutBridge()
    imap._client = bridge.client
    return imap, bridge

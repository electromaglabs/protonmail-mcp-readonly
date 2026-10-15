"""Låtsas-Bridge för efterfix-live: beteenden som livetestet mot riktiga Bridge visade.

Bygger på LabelBridge (tests/feat_etiketter_bridge.py) och lägger till:

- Permanent radering i Trash/Drafts (UID EXPUNGE på \\Deleted-UID:n) tar bort
  mejlet helt, ur alla vyer inklusive All Mail — som när Bridge anropar
  DeleteMessage.
- ``no_then_vanish``: Bridge svarar NO på UID EXPUNGE i en vy (som "failed to
  unlabel messages: Message does not exist (Code=2501)") men mejlen försvinner
  ändå ur vyn några SELECT senare, när Bridge hämtat händelserna från Proton
  (var 20:e–40:e sekund). Vanliga mejl försvinner då helt. Utkast blir kvar i
  All Mail utan mapp (föräldralösa) — så såg det ut live.
- \\Flagged tas bort direkt, men mejlet ligger kvar i Starred-vyn tills det
  tas bort därifrån (Starred-vyn uppdateras först vid nästa händelse).
"""
from __future__ import annotations

from tests.feat_etiketter_bridge import LabelBridge, _no, _ok, make_client as _make_client

CODE_2501 = "failed to unlabel messages: Message does not exist (Code=2501, Status=0)"


class LiveBridge(LabelBridge):
    def __init__(self) -> None:
        super().__init__()
        # vy -> (antal SELECT innan mejlen försvinner, hur många EXPUNGE som nekas)
        self.no_then_vanish: dict[str, list[int]] = {}
        self._pending: list[tuple[str, list[str], int]] = []  # (vy, uid:n, SELECT kvar)
        self.orphans: set[str] = set()  # Message-ID för föräldralösa utkast

    def put_mail(self, view: str, uid: str, message_id: str, *, draft: bool = False,
                 all_mail_uid: str | None = None, flags: tuple[str, ...] = ()) -> None:
        """Mejlet i vyn och (om all_mail_uid anges) i All Mail."""
        self.put(view, uid, message_id)
        msg_flags = self.messages[message_id]["flags"]
        msg_flags.update(flags)
        if draft:
            msg_flags.add("\\Draft")
        if all_mail_uid:
            self.put("All Mail", all_mail_uid, message_id)

    def _remove_everywhere(self, message_id: str) -> None:
        for view, uids in self.views.items():
            for uid, mid in list(uids.items()):
                if mid == message_id:
                    self._detach(view, uid)

    async def _select(self, quoted: str):
        name = self._name(quoted)
        still: list[tuple[str, list[str], int]] = []
        for view, uids, left in self._pending:
            if view == name and left <= 1:
                for uid in uids:
                    mid = self.views[view].get(uid)
                    if mid is None:
                        continue
                    if "\\Draft" in self.messages[mid]["flags"]:
                        # Utkastet tappar platsen men raderas inte: kvar i All Mail
                        self._detach(view, uid)
                        self.orphans.add(mid)
                    else:
                        self._remove_everywhere(mid)
            elif view == name:
                still.append((view, uids, left - 1))
            else:
                still.append((view, uids, left))
        self._pending = still
        return await super()._select(quoted)

    async def _uid(self, command: str, *args: str):
        cmd = command.upper()
        view = self.selected
        if cmd == "EXPUNGE" and cmd not in self.refuse:
            uids = [u for u in self._uid_set(args[0]) if u in self.views[view] and (view, u) in self.deleted]
            rule = self.no_then_vanish.get(view)
            if rule and rule[1] > 0:
                rule[1] -= 1
                self.commands.append((f"UID {cmd}", *args))
                self._pending.append((view, uids, rule[0]))
                return _no(CODE_2501)
            if view in ("Trash", "Drafts"):
                self.commands.append((f"UID {cmd}", *args))
                for u in uids:
                    self._remove_everywhere(self.views[view][u])
                return _ok()
        return await super()._uid(command, *args)


def make_client(monkeypatch):
    imap, _ = _make_client(monkeypatch)
    bridge = LiveBridge()
    imap._client = bridge.client
    return imap, bridge

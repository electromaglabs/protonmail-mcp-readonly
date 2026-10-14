"""Falsk brevlåda för fix-sok-testerna: SEARCH och FETCH som Bridge.

Bridge (Gluon) jämför SUBJECT/FROM mot de *okodade* headervärdena, utan
RFC 2047-avkodning. Den här fejken gör likadant, så att testerna visar
samma beteende som riktiga Bridge.
"""
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock



def imap_mock() -> AsyncMock:
    """aioimaplib.IMAP4-attrapp: inloggad, SELECT svarar OK (som _imap_mock i test_imap_client.py)."""
    m = AsyncMock()
    m.select.return_value = SimpleNamespace(result="OK", lines=[])
    m.login.return_value = SimpleNamespace(result="OK", lines=[])
    m.protocol = MagicMock()
    m.protocol.state = "SELECTED"
    return m


_TERM_RE = re.compile(r'(SUBJECT|FROM) "((?:[^"\\]|\\.)*)"')


class FakeMailbox:
    def __init__(self):
        self.messages = []  # (seq, uid, raw_subject, raw_from)

    def add(self, uid, subject="", sender="x@example.com"):
        self.messages.append((len(self.messages) + 1, int(uid), subject, sender))

    def fill(self, count, subject="Vanligt brev"):
        for _ in range(count):
            self.add(1000 + len(self.messages), subject)

    def install(self, imap_client):
        imap_client._client.select = AsyncMock(return_value=SimpleNamespace(
            result="OK", lines=[f"{len(self.messages)} EXISTS".encode()]))
        imap_client._client.search = AsyncMock(side_effect=self._search)
        imap_client._client.fetch = AsyncMock(side_effect=self._fetch)

    async def _search(self, criteria, *args, **kwargs):
        hits = []
        terms = _TERM_RE.findall(criteria)
        for seq, _uid, subject, sender in self.messages:
            raw = {"SUBJECT": subject, "FROM": sender}
            if all(term.lower() in raw[key].lower() for key, term in terms):
                hits.append(str(seq))
        return SimpleNamespace(result="OK", lines=[" ".join(hits).encode(), b"SEARCH completed"])

    async def _fetch(self, message_set, parts, **kwargs):
        wanted = {int(s) for s in message_set.split(",")}
        lines = []
        for seq, uid, subject, sender in self.messages:
            if seq in wanted:
                data = f"Subject: {subject}\r\nFrom: {sender}\r\n\r\n".encode()
                lines += [
                    f"{seq} FETCH (UID {uid} FLAGS () BODY[HEADER.FIELDS (DATE FROM SUBJECT)] {{{len(data)}}}".encode(),
                    bytearray(data),
                    b")",
                ]
        return SimpleNamespace(result="OK", lines=lines)

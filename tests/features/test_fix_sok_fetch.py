"""BDD-tester: robust tolkning av FETCH-svaret i sökningen (fix-sok, N7 + UID efter literal)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.imap_client import IMAPClient

scenarios("fix_sok_fetch.feature")


@pytest.fixture
def imap(monkeypatch):
    monkeypatch.setenv("PROTONMAIL_USERNAME", "user")
    monkeypatch.setenv("PROTONMAIL_PASSWORD", "pass")
    from protonmail_mcp.config import Settings
    client = IMAPClient(Settings(_env_file=None))
    client._client = AsyncMock()
    client._client.select = AsyncMock(return_value=SimpleNamespace(result="OK", lines=[b"2 EXISTS"]))
    return client


def _message(seq, uid, subject):
    return [
        f"{seq} FETCH (UID {uid} FLAGS () BODY[HEADER.FIELDS (DATE FROM SUBJECT)] {{20}}".encode(),
        bytearray(f"Subject: {subject}\r\n\r\n".encode()),
        b")",
    ]


def _respond(imap, seqnums, lines):
    imap._client.search = AsyncMock(
        return_value=SimpleNamespace(result="OK", lines=[" ".join(seqnums).encode()]))
    imap._client.fetch = AsyncMock(return_value=SimpleNamespace(result="OK", lines=lines))


@given(parsers.parse('att en sökning i INBOX träffar brev 1 och 2 med UID "{uid1}" och "{uid2}"'),
       target_fixture="lines")
def two_hits(imap, uid1, uid2):
    lines = _message(1, uid1, "Ett") + _message(2, uid2, "Två")
    _respond(imap, ["1", "2"], lines)
    return lines


@given(parsers.parse('servern skickar en oombedd flaggändring för UID "{uid}" mitt i svaret'))
def unsolicited(imap, lines, uid):
    lines[3:3] = [f"1 FETCH (UID {uid} FLAGS (\\Seen))".encode()]


@given(parsers.parse('servern skickar brevet med UID "{uid}" en gång till'))
def duplicate(imap, lines, uid):
    lines += _message(1, uid, "Ett")


@given(parsers.parse('att servern lägger UID efter header-datat för brevet med UID "{uid}"'))
def uid_after_literal(imap, uid):
    _respond(imap, ["6718"], [
        b"6718 FETCH (FLAGS () BODY[HEADER.FIELDS (DATE FROM SUBJECT)] {13}",
        bytearray(b"Subject: Hej\r\n\r\n"),
        f" UID {uid})".encode(),
    ])


@when("jag söker efter olästa brev", target_fixture="hits")
def search_unseen(imap):
    result = asyncio.run(imap.search_messages("INBOX", unseen=True))
    return result["messages"] if isinstance(result, dict) else result


@then(parsers.parse('ska träffarna ha UID {uids}'))
def hits_have_uids(hits, uids):
    expected = [u.strip().strip('"') for u in uids.replace(" och ", ",").split(",")]
    assert [h["uid"] for h in hits] == expected


@then(parsers.parse('ska träffen ha ämnet "{subject}"'))
def hit_subject(hits, subject):
    assert hits[0]["subject"] == subject

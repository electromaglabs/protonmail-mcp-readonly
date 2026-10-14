"""Konversationer (trådar) för ett mejl, byggda av Message-ID-kedjan.

Bridge saknar IMAP THREAD, så tråden byggs här: Message-ID, In-Reply-To och
References för mejlet ger en uppsättning ID:n, och All Mail söks efter mejl
som har ett av dem som Message-ID eller som refererar till något av dem.
Nya mejl ger nya ID:n, och sökningen upprepas tills inget nytt hittas (med
tak för antal rundor och antal mejl). All Mail används för att få med både
mottagna och skickade mejl.

Verifierat live (läs-endast): HEADER Message-ID/In-Reply-To/References-sökning
fungerar i All Mail och tar 3–8 s per SEARCH på ~32 000 mejl; en OR-kedja med
flera ID:n tar ungefär lika lång tid som ett enda.
"""
from __future__ import annotations

import re
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any

from .imap_client import (
    _FETCH_CHUNK_SIZE,
    _CONTROL_CHAR_RE,
    _imap_quoted,
    _parse_fetch_metadata,
    _quote_mailbox,
    _require_ok,
    _serialized,
    _validate_uid,
)

ALL_MAIL = "All Mail"
# Högst så många sökrundor (varje runda är 1+ SEARCH i All Mail, 3–8 s styck)
_MAX_ROUNDS = 6
# Så många ID:n per SEARCH; varje ID ger tre HEADER-nycklar i OR-kedjan
_IDS_PER_SEARCH = 20
_MAX_LIMIT = 200
_THREAD_FIELDS = "DATE FROM TO CC SUBJECT MESSAGE-ID IN-REPLY-TO REFERENCES"
_EXTRA = ("cc", "in-reply-to", "references")
# msg-id enligt RFC 5322: "<" id-left "@" id-right ">"; i praktiken allt utom
# blanktecken, vinkelparenteser och citattecken (som skulle kräva escaping)
_MSG_ID_RE = re.compile(r'<[^<>\s"\\]+>')
# Bridge lägger Protons eget meddelande-ID i References. Det är inget
# Message-ID och pekar bara på mejlet självt (kontrollerat live).
_PROTON_INTERNAL_SUFFIX = "@protonmail.internalid>"
_MAX_ID_LENGTH = 998


def _message_ids(*values: str | None) -> list[str]:
    """Alla msg-id i värdena, i ordning och utan dubbletter."""
    ids: list[str] = []
    for value in values:
        for msg_id in _MSG_ID_RE.findall(value or ""):
            if (
                msg_id not in ids
                and len(msg_id) <= _MAX_ID_LENGTH
                and not _CONTROL_CHAR_RE.search(msg_id)
                and not msg_id.lower().endswith(_PROTON_INTERNAL_SUFFIX)
            ):
                ids.append(msg_id)
    return ids


def _thread_criteria(ids: list[str]) -> list[str]:
    """SEARCH-kriterier: mejl med något av ID:na som Message-ID, In-Reply-To eller References."""
    keys: list[list[str]] = []
    for msg_id in ids:
        quoted = _imap_quoted(msg_id, "Message-ID")
        for header in ("Message-ID", "In-Reply-To", "References"):
            keys.append(["HEADER", header, quoted])
    criteria: list[str] = []
    for i, key in enumerate(keys):
        if i < len(keys) - 1:
            criteria.append("OR")
        criteria += key
    return criteria


def _ids_of(meta: dict[str, Any]) -> list[str]:
    return _message_ids(meta["message_id"], meta.get("in_reply_to"), meta.get("references"))


def _belongs(meta: dict[str, Any], known: set[str]) -> bool:
    """Exakt kontroll: servern söker delsträngar, så "<a@x>" träffar även "<ba@x>"."""
    return any(msg_id in known for msg_id in _ids_of(meta))


def _date_key(meta: dict[str, Any]) -> tuple[int, float, int]:
    """Sorteringsnyckel: datum (UTC), mejl utan tolkbart datum sist, sedan UID."""
    uid = int(meta["uid"]) if meta["uid"].isdigit() else 0
    try:
        when = parsedate_to_datetime(meta["date"])
    except (TypeError, ValueError, IndexError):
        return (1, 0.0, uid)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (0, when.timestamp(), uid)


def _public(meta: dict[str, Any], mailbox: str) -> dict[str, Any]:
    out = {k: v for k, v in meta.items() if k != "references"}
    out["mailbox"] = mailbox
    return out


async def _fetch_thread_metadata(imap, seqnums: list[str]) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    for start in range(0, len(seqnums), _FETCH_CHUNK_SIZE):
        chunk = seqnums[start:start + _FETCH_CHUNK_SIZE]
        resp = await imap._client.fetch(
            ",".join(chunk), f"(UID FLAGS BODY.PEEK[HEADER.FIELDS ({_THREAD_FIELDS})])"
        )
        _require_ok(resp, f"Hämtningen av konversationens mejl i {ALL_MAIL}")
        msgs += _parse_fetch_metadata(resp.lines, extra_headers=_EXTRA)
    return msgs


@_serialized
async def get_thread(imap, uid: str, mailbox: str, max_messages: int = 50) -> dict[str, Any]:
    """Hämtar konversationen som mejlet uid i mailbox ingår i, sorterad på datum.

    Returnerar dict med mailbox ("All Mail"), messages (metadata: uid i All
    Mail, mailbox, from, to, cc, subject, date, message_id, in_reply_to,
    flags; äldst först), total (antal hittade mejl), complete och note.
    Med fler än max_messages träffar returneras startmejlet och de senaste.
    """
    safe_uid = _validate_uid(uid)
    _quote_mailbox(mailbox)
    if isinstance(max_messages, bool) or not isinstance(max_messages, int) or not 1 <= max_messages <= _MAX_LIMIT:
        raise ValueError(f"max_messages måste vara ett heltal 1–{_MAX_LIMIT} (fick {max_messages!r})")

    await imap._ensure_connected()
    await imap._select(mailbox)
    resp = await imap._uid("fetch", safe_uid, f"(UID FLAGS BODY.PEEK[HEADER.FIELDS ({_THREAD_FIELDS})])")
    _require_ok(resp, f"Hämtningen av UID {safe_uid} i {mailbox}")
    start = next((m for m in _parse_fetch_metadata(resp.lines, extra_headers=_EXTRA) if m["uid"] == safe_uid), None)
    if start is None:
        raise ValueError(
            f"Inget meddelande med UID {safe_uid} i {mailbox}. "
            "UID:n gäller per mapp — kontrollera att mailbox är samma mapp som UID:t kom från."
        )

    own_id = _message_ids(start["message_id"])
    if not own_id:
        return {
            "mailbox": mailbox,
            "messages": [_public(start, mailbox)],
            "total": 1,
            "complete": False,
            "note": (
                "Mejlet saknar Message-ID, så konversationen kan inte sökas fram. "
                "Bara mejlet självt returneras."
            ),
        }

    await imap._select(ALL_MAIL)
    known: list[str] = _ids_of(start)
    searched: set[str] = set()
    seen_seqnums: set[str] = set()
    found: dict[str, dict[str, Any]] = {}
    limited = False
    for _ in range(_MAX_ROUNDS):
        pending = [msg_id for msg_id in known if msg_id not in searched]
        if not pending:
            break
        hits: set[str] = set()
        for i in range(0, len(pending), _IDS_PER_SEARCH):
            hits |= set(await imap._search_seqnums(_thread_criteria(pending[i:i + _IDS_PER_SEARCH])))
        searched.update(pending)
        new = sorted(hits - seen_seqnums, key=int)
        seen_seqnums.update(new)
        known_set = set(known)
        for meta in await _fetch_thread_metadata(imap, new):
            if not _belongs(meta, known_set):
                continue
            found[meta["uid"]] = meta
            for msg_id in _ids_of(meta):
                if msg_id not in known_set:
                    known.append(msg_id)
                    known_set.add(msg_id)
        if len(found) > max_messages:
            limited = True
            break
    unsearched = [msg_id for msg_id in known if msg_id not in searched]

    messages = sorted(found.values(), key=_date_key)
    start_in_all_mail = next((m for m in messages if own_id[0] in _message_ids(m["message_id"])), None)
    notes: list[str] = []
    if len(messages) > max_messages:
        keep = messages[-max_messages:]
        if start_in_all_mail is not None and start_in_all_mail not in keep:
            keep = [start_in_all_mail, *messages[-(max_messages - 1):]] if max_messages > 1 else [start_in_all_mail]
        messages = sorted(keep, key=_date_key)
        notes.append(
            f"Konversationen har fler mejl än max_messages ({max_messages}); "
            "startmejlet och de senaste returneras."
        )
    elif limited or unsearched:
        notes.append("Sökningen avbröts efter maximalt antal rundor; fler mejl kan finnas.")
    if start_in_all_mail is None:
        notes.append(f"Startmejlet hittades inte i {ALL_MAIL}.")

    return {
        "mailbox": ALL_MAIL,
        "messages": [_public(m, ALL_MAIL) for m in messages],
        "total": len(found),
        "complete": not (limited or unsearched or len(found) > max_messages),
        "note": " ".join(notes) or None,
    }

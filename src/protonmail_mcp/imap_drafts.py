"""Utkast i Drafts via IMAP APPEND.

Bridge gör ett APPEND till Drafts till ett riktigt utkast i Proton, som syns
och kan redigeras och skickas i Protons appar. EXPUNGE i Drafts raderar
permanent. Funktionerna här tar IMAPClient som första argument och körs under
klientens lås (``_serialized``), som metoderna i IMAPClient.
"""
from __future__ import annotations

import asyncio
import re

from .imap_client import (
    IMAPClient,
    _UID_RE,
    _decode,
    _imap_quoted,
    _quote_mailbox,
    _require_ok,
    _serialized,
    _validate_uid,
)

DRAFTS = "Drafts"
# Bridge sätter alltid \Seen på utkast; \Draft gör det till ett utkast
_DRAFT_FLAGS = r"(\Draft \Seen)"
# Svarskod från UIDPLUS (RFC 4315): [APPENDUID <uidvalidity> <uid>]
_APPENDUID_RE = re.compile(r"\[APPENDUID\s+\d+\s+(\d+)\]", re.IGNORECASE)


async def _append(imap: IMAPClient, message: bytes):
    """APPEND till Drafts med timeout (aioimaplib har ingen egen för APPEND)."""
    try:
        return await asyncio.wait_for(
            imap._client.append(message, mailbox=_quote_mailbox(DRAFTS), flags=_DRAFT_FLAGS),
            imap.uid_timeout,
        )
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError(
            f"ProtonMail Bridge svarade inte på APPEND till {DRAFTS} inom {imap.uid_timeout:g} s"
        ) from None


def _appenduid(resp) -> str | None:
    for line in resp.lines:
        m = _APPENDUID_RE.search(_decode(line))
        if m:
            return m.group(1)
    return None


async def _find_by_message_id(imap: IMAPClient, message_id: str) -> str | None:
    """UID för utkastet med det här Message-ID:t i Drafts (det nyaste om flera).

    Används bara när Bridge inte svarar med APPENDUID. Utkastet är då redan
    sparat, så ett fel här ger None i stället för ett fel — annars kunde den
    som anropar tro att inget sparades och skapa ett till.
    """
    try:
        criteria = ["HEADER", "Message-ID", _imap_quoted(message_id, "Message-ID")]
        await imap._select(DRAFTS)
        seqnums = await imap._search_seqnums(criteria)
        if not seqnums:
            return None
        resp = await imap._client.fetch(",".join(seqnums), "(UID)")
    except ValueError:
        return None
    if resp.result != "OK":
        return None
    uids = [int(m.group(1)) for line in resp.lines if (m := _UID_RE.search(_decode(line)))]
    return str(max(uids)) if uids else None


async def _store_draft(imap: IMAPClient, message: bytes, message_id: str | None) -> str | None:
    resp = await _append(imap, message)
    _require_ok(resp, f"Sparandet av utkastet i {DRAFTS}")
    uid = _appenduid(resp)
    if uid is None and message_id:
        uid = await _find_by_message_id(imap, message_id)
    return uid


@_serialized
async def append_draft(imap: IMAPClient, message: bytes, message_id: str | None) -> str | None:
    """Lägg ett färdigt meddelande i Drafts som utkast (flaggorna \\Draft \\Seen).

    Returnerar utkastets UID i Drafts: ur APPENDUID om Bridge svarar med det,
    annars genom att söka upp Message-ID:t. None om UID:t inte gick att få fram
    (utkastet är ändå sparat). Kastar ValueError om Bridge vägrar spara.
    """
    await imap._ensure_connected()
    return await _store_draft(imap, message, message_id)


async def _delete_permanently(imap: IMAPClient, uid: str) -> None:
    """Radera ett utkast permanent med den befintliga vägen i IMAPClient.

    delete_message(permanent=True) gör UID STORE \\Deleted + UID EXPUNGE på
    just det UID:t (aldrig EXPUNGE på hela mappen) och tar bort \\Deleted igen
    om EXPUNGE misslyckas. Låset hålls redan här, så den odekorerade metoden
    anropas (``_serialized`` använder functools.wraps, som sparar __wrapped__).
    """
    await IMAPClient.delete_message.__wrapped__(imap, DRAFTS, uid, permanent=True)


@_serialized
async def replace_draft(
    imap: IMAPClient, old_uid: str, message: bytes, message_id: str | None
) -> str | None:
    """Ersätt utkastet old_uid i Drafts med ett nytt meddelande.

    Ordningen gör att inget går förlorat: först kontrolleras att det gamla
    utkastet finns, sedan sparas det nya med APPEND, och först när det lyckats
    raderas det gamla permanent. Misslyckas APPEND rörs det gamla inte.
    Returnerar det nya utkastets UID (None om Bridge inte angav det).
    """
    safe_uid = _validate_uid(old_uid)
    await imap._ensure_connected()
    await imap._select(DRAFTS)
    await imap._require_uid(DRAFTS, safe_uid)
    new_uid = await _store_draft(imap, message, message_id)
    try:
        await _delete_permanently(imap, safe_uid)
    except ValueError as exc:
        raise ValueError(
            f"Det nya utkastet sparades i {DRAFTS} (UID {new_uid}), men det gamla "
            f"(UID {safe_uid}) kunde inte tas bort, så båda finns kvar: {exc}"
        ) from exc
    return new_uid

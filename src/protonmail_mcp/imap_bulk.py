"""Gemensamt för IMAP-operationer på flera UID:n i samma mapp.

Resultatet har formen {"ok": [uid, ...], "failed": [{"uid": ..., "error": ...}]},
med UID:na i den ordning de angavs. Formatfel (ogiltigt UID, för många UID:n)
ger ValueError för hela anropet innan Bridge kontaktas; fel som gäller ett
enskilt mejl (finns inte, Bridge nekar) hamnar i "failed".
"""
from typing import Any

from .imap_client import (
    _READD_DELETES,
    _UID_RE,
    IMAPClient,
    _check_move,
    _decode,
    _mailbox_key,
    _quote_mailbox,
    _require_ok,
    _response_text,
    _serialized,
    _validate_uid,
)

MAX_UIDS = 100

BulkResult = dict[str, Any]


def validate_uids(uids: list[str]) -> list[str]:
    """Validerar varje UID och tar bort dubbletter (första förekomsten behålls)."""
    if not uids:
        raise ValueError("Ange minst ett UID")
    if len(uids) > MAX_UIDS:
        raise ValueError(f"För många UID:n ({len(uids)}) — högst {MAX_UIDS} per anrop")
    unique: list[str] = []
    for uid in uids:
        _strict_uid(uid)
        if uid not in unique:
            unique.append(uid)
    return unique


def _strict_uid(uid) -> str:
    # isascii/isdigit utöver _validate_uid: UID:na sätts ihop till ett UID-set,
    # så ett avslutande radbyte eller en Unicode-siffra får inte slinka igenom
    if not (isinstance(uid, str) and uid.isascii() and uid.isdigit()):
        raise ValueError(f"Ogiltigt UID: {uid!r} — måste vara ett heltal")
    return _validate_uid(uid)


def uid_set(uids: list[str]) -> str:
    """UID-set för ett IMAP-kommando, t.ex. "1,5,9". Varje UID valideras igen."""
    if not uids:
        raise ValueError("Tomt UID-set")
    return ",".join(_strict_uid(uid) for uid in uids)


def missing_error(uid: str, mailbox: str) -> str:
    return (
        f"Inget meddelande med UID {uid} i {mailbox}. "
        "UID:n gäller per mapp — kontrollera att mailbox är samma mapp som UID:t kom från."
    )


def result(uids: list[str], ok: list[str], failed: list[dict[str, str]]) -> BulkResult:
    """Sorterar ok och failed i samma ordning som uids."""
    order = {uid: i for i, uid in enumerate(uids)}
    return {
        "ok": sorted(set(ok), key=order.__getitem__),
        "failed": sorted(failed, key=lambda f: order[f["uid"]]),
    }


def single(res: BulkResult) -> bool:
    """Returform för ett enskilt UID: True, eller ValueError med felet."""
    if res["failed"]:
        raise ValueError(res["failed"][0]["error"])
    return True


async def existing_uids(imap: IMAPClient, mailbox: str, uids: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Delar upp UID:na i de som finns i den valda mappen och de som saknas.

    Bridge svarar OK på UID STORE/COPY/MOVE/EXPUNGE även för UID:n som inte
    finns, så utan kontrollen skulle de rapporteras som lyckade. Ett nekat
    FETCH ger ValueError för hela anropet — då har inget skrivits.
    """
    resp = await imap._uid("fetch", uid_set(uids), "(UID)")
    _require_ok(resp, f"Kontrollen av UID:n i {mailbox}")
    seen: set[int] = set()
    for line in resp.lines:
        m = _UID_RE.search(_decode(line))
        if m:
            seen.add(int(m.group(1)))
    found = [uid for uid in uids if int(uid) in seen]
    missing = [{"uid": uid, "error": missing_error(uid, mailbox)} for uid in uids if int(uid) not in seen]
    return found, missing


def fail_all(uids: list[str], error: str) -> list[dict[str, str]]:
    return [{"uid": uid, "error": error} for uid in uids]


def _failure(what: str, resp) -> str:
    return f"{what} misslyckades ({resp.result}): {_response_text(resp)}"


async def _split_after_failure(
    imap: IMAPClient, mailbox: str, uids: list[str], error: str
) -> tuple[list[str], list[dict[str, str]]]:
    """Efter ett nekat MOVE/EXPUNGE: de UID:n som är kvar i mappen misslyckades.

    Bridge kan ha hunnit genomföra en del av kommandot; de UID:n som inte
    längre finns i mappen räknas som klara. Går det inte att kontrollera
    räknas alla som misslyckade.
    """
    try:
        left, _ = await existing_uids(imap, mailbox, uids)
    except ValueError as exc:
        return [], fail_all(uids, f"{error} (kunde inte kontrollera vilka som genomfördes: {exc})")
    left_set = set(left)
    return [u for u in uids if u not in left_set], fail_all(left, error)


async def store_flags(
    imap: IMAPClient, mailbox: str, uids: list[str], flags: str, add: bool, what: str
) -> BulkResult:
    """UID STORE ±FLAGS på de UID:n som finns i mailbox, i ett kommando. Kräver låset."""
    uids = validate_uids(uids)
    _quote_mailbox(mailbox)
    await imap._ensure_connected()
    await imap._select(mailbox)
    found, failed = await existing_uids(imap, mailbox, uids)
    ok: list[str] = []
    if found:
        resp = await imap._uid("store", uid_set(found), "+FLAGS" if add else "-FLAGS", flags)
        if resp.result == "OK":
            ok = found
        else:
            failed += fail_all(found, _failure(f"{what} i {mailbox}", resp))
    return result(uids, ok, failed)


@_serialized
async def set_flags(imap: IMAPClient, mailbox: str, uids: list[str], flags: str, add: bool) -> BulkResult:
    """Sätter eller tar bort flaggor (t.ex. \\Seen) på flera mejl i samma mapp."""
    return await store_flags(imap, mailbox, uids, flags, add, "Ändringen av flaggorna")


async def _move_found(imap: IMAPClient, mailbox: str, uids: list[str], target: str) -> BulkResult:
    quoted_target = _quote_mailbox(target)
    await imap._ensure_connected()
    await imap._select(mailbox)
    found, failed = await existing_uids(imap, mailbox, uids)
    ok: list[str] = []
    if found:
        resp = await imap._uid("move", uid_set(found), quoted_target)
        if resp.result == "OK":
            ok = found
        else:
            ok, more = await _split_after_failure(
                imap, mailbox, found, _failure(f"Flytten från {mailbox} till {target}", resp)
            )
            failed += more
    return result(uids, ok, failed)


@_serialized
async def move(imap: IMAPClient, mailbox: str, uids: list[str], target: str) -> BulkResult:
    """Flyttar flera mejl med ett UID MOVE. Samma vakter som move_message, för alla UID:n."""
    uids = validate_uids(uids)
    _quote_mailbox(mailbox)
    _quote_mailbox(target)
    _check_move(mailbox, target)
    return await _move_found(imap, mailbox, uids, target)


@_serialized
async def delete(imap: IMAPClient, mailbox: str, uids: list[str], permanent: bool = False) -> BulkResult:
    """Flyttar flera mejl till Trash, eller raderar dem permanent ur Trash/Drafts.

    Samma vakter och texter som IMAPClient.delete_message. Permanent radering
    görs med UID STORE \\Deleted + UID EXPUNGE på just de UID:na, aldrig med
    EXPUNGE på hela mappen.
    """
    uids = validate_uids(uids)
    _quote_mailbox(mailbox)
    key = _mailbox_key(mailbox)
    if not permanent:
        if key == "trash":
            raise ValueError(
                "Mejlet ligger redan i Trash. Använd permanent=True för att radera det permanent."
            )
        _check_move(mailbox, "Trash")
        return await _move_found(imap, mailbox, uids, "Trash")

    if key not in _READD_DELETES:
        raise ValueError(
            f"Permanent radering görs bara i Trash eller Drafts, inte i {mailbox}. "
            "Ta bort mejlet utan permanent först, så hamnar det i Trash."
        )
    await imap._ensure_connected()
    await imap._select(mailbox)
    found, failed = await existing_uids(imap, mailbox, uids)
    ok: list[str] = []
    if found:
        targets = uid_set(found)
        resp = await imap._uid("store", targets, "+FLAGS", r"(\Deleted)")
        if resp.result != "OK":
            failed += fail_all(found, _failure(f"Borttagningsmarkeringen i {mailbox}", resp))
            return result(uids, ok, failed)
        resp = await imap._uid("expunge", targets)
        if resp.result == "OK":
            ok = found
        else:
            # Lämna inte \Deleted kvar: nästa EXPUNGE i mappen skulle annars ta mejlen
            await imap._uid("store", targets, "-FLAGS", r"(\Deleted)")
            ok, more = await _split_after_failure(
                imap, mailbox, found, _failure(f"Den permanenta raderingen i {mailbox}", resp)
            )
            failed += more
    return result(uids, ok, failed)

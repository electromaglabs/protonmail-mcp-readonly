"""Gemensamt för IMAP-operationer på flera UID:n i samma mapp.

Resultatet har formen {"ok": [uid, ...], "failed": [{"uid": ..., "error": ...}]},
med UID:na i den ordning de angavs. Formatfel (ogiltigt UID, för många UID:n)
ger ValueError för hela anropet innan Bridge kontaktas; fel som gäller ett
enskilt mejl (finns inte, Bridge nekar) hamnar i "failed".
"""
from typing import Any

from .imap_client import IMAPClient, _decode, _require_ok, _UID_RE, _validate_uid

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

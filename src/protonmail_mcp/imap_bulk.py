"""Gemensamt för IMAP-operationer på flera UID:n i samma mapp.

Resultatet har formen {"ok": [uid, ...], "failed": [{"uid": ..., "error": ...}]},
med UID:na i den ordning de angavs. Formatfel (ogiltigt UID, för många UID:n)
ger ValueError för hela anropet innan Bridge kontaktas; fel som gäller ett
enskilt mejl (finns inte, Bridge nekar) hamnar i "failed".
"""
import asyncio
import logging
import re
import time
from typing import Any

from . import policy

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

logger = logging.getLogger(__name__)

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
@policy.write_operation("set_flags")
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
@policy.write_operation("move")
async def move(imap: IMAPClient, mailbox: str, uids: list[str], target: str) -> BulkResult:
    """Flyttar flera mejl med ett UID MOVE. Samma vakter som move_message, för alla UID:n."""
    uids = validate_uids(uids)
    _quote_mailbox(mailbox)
    _quote_mailbox(target)
    _check_move(mailbox, target)
    return await _move_found(imap, mailbox, uids, target)


@_serialized
@policy.write_operation("delete")
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
        ok, more = await permanent_delete_found(imap, mailbox, found, f"Den permanenta raderingen i {mailbox}")
        failed += more
    return result(uids, ok, failed)


# Bridges svar när Proton-API:t säger "Message does not exist" (go-proton-api,
# UnlabelMessages). Live kom det för en hel omgång permanenta raderingar i
# Trash, och mejlen försvann ändå ur Trash vid Bridges nästa händelsehämtning.
_DOES_NOT_EXIST = "Code=2501"
_FLAGS_RE = re.compile(r"FLAGS\s*\(([^)]*)\)", re.IGNORECASE)
ALL_MAIL = "All Mail"
TRASH = "Trash"


async def permanent_delete_found(
    imap: IMAPClient, mailbox: str, found: list[str], what: str
) -> tuple[list[str], list[dict[str, str]]]:
    """UID STORE \\Deleted + UID EXPUNGE på found, som finns i den valda mappen (Trash/Drafts).

    Returnerar (ok, failed). Nekar Bridge EXPUNGE tas \\Deleted bort igen och
    det kontrolleras vilka UID:n som ändå är borta. Är felet Code=2501
    ("Message does not exist") väntas det, högst imap_client._GONE_TIMEOUT
    sekunder: Bridge kan ha gjort ändringen i Proton och visar den först efter
    nästa händelsehämtning (var 20:e–40:e sekund). Utkast som då försvunnit ur
    mappen men blivit kvar i All Mail utan mapp raderas via Trash
    (_delete_orphaned_drafts). Aldrig EXPUNGE utan UID.
    """
    targets = uid_set(found)
    resp = await imap._uid("store", targets, "+FLAGS", r"(\Deleted)")
    if resp.result != "OK":
        return [], fail_all(found, _failure(f"Borttagningsmarkeringen i {mailbox}", resp))
    resp = await imap._uid("expunge", targets)
    if resp.result == "OK":
        return found, []
    # Lämna inte \Deleted kvar: nästa EXPUNGE i mappen skulle annars ta mejlen
    await imap._uid("store", targets, "-FLAGS", r"(\Deleted)")
    error = _failure(what, resp)
    ok, failed = await _split_after_failure(imap, mailbox, found, error)
    if not failed or _DOES_NOT_EXIST not in _response_text(resp):
        return ok, failed
    left = [f["uid"] for f in failed]
    drafts = await _draft_identities(imap, mailbox, left)
    gone, failed = await _wait_until_gone(imap, mailbox, left, error)
    ok += gone
    vanished = {uid: drafts[uid] for uid in gone if uid in drafts}
    if vanished:
        orphan_failed = await _delete_orphaned_drafts(imap, vanished)
        bad = {f["uid"] for f in orphan_failed}
        ok = [u for u in ok if u not in bad]
        failed += orphan_failed
    return ok, failed


async def _draft_identities(imap: IMAPClient, mailbox: str, uids: list[str]) -> dict[str, dict]:
    """Identitet (Message-ID, tid, storlek) för de UID:n i vald mapp som är utkast.

    Bästa försök: går det inte att avgöra blir svaret tomt, och då görs ingen
    återställning av föräldralösa utkast.
    """
    from .imap_labels import _fetch_identities_by_uid  # imap_labels bygger på den här modulen

    try:
        resp = await imap._uid("fetch", uid_set(uids), "(UID FLAGS)")
        if resp.result != "OK":
            return {}
        drafts = []
        for line in resp.lines:
            text = _decode(line)
            uid_m, flags_m = _UID_RE.search(text), _FLAGS_RE.search(text)
            if uid_m and flags_m and "\\draft" in flags_m.group(1).casefold().split():
                drafts.append(uid_m.group(1))
        if not drafts:
            return {}
        identities = await _fetch_identities_by_uid(imap, mailbox, drafts)
    except ValueError:
        return {}
    return {uid: info for uid, info in identities.items() if uid in drafts and info["message_id"]}


async def _wait_until_gone(
    imap: IMAPClient, mailbox: str, uids: list[str], error: str
) -> tuple[list[str], list[dict[str, str]]]:
    """Väntar tills UID:na inte längre finns i mailbox, högst _GONE_TIMEOUT sekunder.

    Mappen väljs om inför varje kontroll, så att Bridges köade ändringar syns.
    Returnerar (borta, failed med error för de som finns kvar).
    """
    from . import imap_client  # läses vid anropet, så att testerna kan korta tiderna

    timeout = imap_client._GONE_TIMEOUT
    deadline = time.monotonic() + timeout
    left = uids
    while True:
        await asyncio.sleep(imap_client._GONE_INTERVAL)
        try:
            await imap._select(mailbox)
            left, _ = await existing_uids(imap, mailbox, left)
        except ValueError as exc:
            return [], fail_all(uids, f"{error} (kunde inte kontrollera vilka som genomfördes: {exc})")
        if not left or time.monotonic() >= deadline:
            break
    left_set = set(left)
    note = f" Mejlet finns kvar i {mailbox} efter {timeout:g} s väntan på att Bridge skulle ta bort det."
    return [u for u in uids if u not in left_set], fail_all(left, error + note)


async def _delete_orphaned_drafts(imap: IMAPClient, drafts: dict[str, dict]) -> list[dict[str, str]]:
    """Raderar utkast som försvann ur Trash/Drafts men blev kvar i All Mail utan mapp.

    Live: när Bridge svarat NO (Code=2501) på permanent radering av ett utkast
    i Trash tog Proton bort Trash från utkastet men raderade det inte, så det
    låg kvar i All Mail, osynligt i Drafts och Trash. Bridge raderar bara när
    EXPUNGE lyckas (connector.go: RemoveMessagesFromMailbox → DeleteMessage).
    Utkastet läggs därför i Trash igen med UID COPY från All Mail och raderas
    där med UID STORE \\Deleted + UID EXPUNGE på just det UID:t. Returnerar
    failed för utkast som inte gick att radera.
    """
    from .imap_labels import _find_in_label  # imap_labels bygger på den här modulen

    try:
        await imap._select(ALL_MAIL)
        orphans, _ = await _find_in_label(imap, ALL_MAIL, drafts)
    except ValueError as exc:
        logger.warning("Kunde inte leta efter föräldralösa utkast i All Mail: %s", exc)
        return []
    failed = []
    for src_uid, all_mail_uid in orphans.items():
        problem = await _delete_orphan(imap, src_uid, all_mail_uid, drafts[src_uid])
        if problem:
            failed.append({"uid": src_uid, "error": (
                f"Utkastet med UID {src_uid} försvann ur mappen men Proton raderade det inte: "
                f"det låg kvar i All Mail utan mapp (UID {all_mail_uid} där). Ett nytt försök "
                f"via Trash misslyckades: {problem}. Utkastet kan ligga kvar i Trash eller "
                "bara i All Mail."
            )})
    return failed


async def _delete_orphan(imap: IMAPClient, src_uid: str, all_mail_uid: str, identity: dict) -> str | None:
    """COPY från All Mail till Trash och permanent radering där. None om det gick."""
    from .imap_labels import _find_in_label

    resp = await imap._uid("copy", uid_set([all_mail_uid]), _quote_mailbox(TRASH))
    if resp.result != "OK":
        return _failure(f"Kopieringen till {TRASH}", resp)
    await imap._select(TRASH)
    found, errors = await _find_in_label(imap, TRASH, {src_uid: identity})
    if src_uid not in found:
        return f"utkastet hittades inte i {TRASH} efter kopieringen"
    trash_uid = uid_set([found[src_uid]])
    resp = await imap._uid("store", trash_uid, "+FLAGS", r"(\Deleted)")
    if resp.result != "OK":
        return _failure(f"Borttagningsmarkeringen i {TRASH}", resp)
    resp = await imap._uid("expunge", trash_uid)
    if resp.result != "OK":
        await imap._uid("store", trash_uid, "-FLAGS", r"(\Deleted)")
        return _failure(f"Den permanenta raderingen i {TRASH}", resp)
    return None

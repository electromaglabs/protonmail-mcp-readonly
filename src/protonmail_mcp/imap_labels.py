"""Etiketter och stjärnmärkning i Proton via Bridge.

Bridge-semantik (se rapport-proton.md, "Sammanfattning: Bridge-semantik"):
- UID COPY till Labels/X lägger till etiketten; mejlet ligger kvar i sin mapp.
- UID EXPUNGE i Labels/X tar bara bort etiketten, inget annat.
- \\Flagged är samma sak som Starred, globalt i alla vyer.
- UID:n gäller per vy: mejlet har ett UID i INBOX och ett annat i Labels/X.

Funktionerna är modulnivåfunktioner med IMAPClient som första argument och
körs under klientens lås (_serialized), som IMAPClient:s egna metoder.
"""
import re
from email.parser import BytesHeaderParser
from typing import Any

from .imap_bulk import (
    BulkResult,
    existing_uids,
    fail_all,
    missing_error,
    result,
    store_flags,
    uid_set,
    validate_uids,
)
from .imap_client import (
    _FETCH_CHUNK_SIZE,
    _FETCH_START_RE,
    _LITERAL_END_RE,
    _UID_RE,
    IMAPClient,
    _check_user_folder,
    _decode,
    _imap_quoted,
    _mailbox_key,
    _quote_mailbox,
    _require_ok,
    _response_text,
    _serialized,
)

LABEL_PREFIX = "Labels/"
# Systemmappar (och behållarna Folders/Labels) som inte är etiketter
_NOT_LABELS = ("inbox", "archive", "sent", "spam", "trash", "drafts", "all mail", "folders", "labels")
# Mejlets identitet i en vy. Samma mejl har samma värden i alla vyer (verifierat
# live mot Bridge); två mejl med samma Message-ID (t.ex. ett mejl till sig själv,
# där kopian i Sent och den i INBOX är två mejl) skiljs åt på tid och storlek.
_IDENTITY_ITEMS = "(UID INTERNALDATE RFC822.SIZE BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])"
_INTERNALDATE_RE = re.compile(r'INTERNALDATE\s+"([^"]*)"', re.IGNORECASE)
_SIZE_RE = re.compile(r'RFC822\.SIZE\s+(\d+)', re.IGNORECASE)
# Så många Message-ID per SEARCH (OR-kedja); Bridge går igenom hela vyn per sökning
_SEARCH_GROUP = 20


def label_mailbox(label: str) -> str:
    """Gör ett etikettnamn ("X" eller "Labels/X") till vynamnet "Labels/X".

    Kastar ValueError för Starred (stjärnmärkning, inte etikett), mappar
    (Folders/…), systemmappar, tomma namn och underetiketter.
    """
    name = label.strip()
    key = name.casefold()
    if key.startswith(LABEL_PREFIX.casefold()):
        name = LABEL_PREFIX + name[len(LABEL_PREFIX):].strip()
        key = name.casefold()
    bare = key[len(LABEL_PREFIX):] if key.startswith(LABEL_PREFIX.casefold()) else key
    if bare == "starred":
        raise ValueError(
            "Starred är Protons stjärnmärkning, inte en etikett. "
            "Använd flag_email för att stjärnmärka och unflag_email för att ta bort stjärnan."
        )
    if key.startswith("folders/"):
        raise ValueError(
            f"{label!r} är en mapp, inte en etikett. Ett mejl ligger i exakt en mapp — "
            "använd move_email för att flytta det dit."
        )
    if bare in _NOT_LABELS and not key.startswith(LABEL_PREFIX.casefold()):
        raise ValueError(
            f"{label!r} är en systemmapp, inte en etikett. Använd move_email för att flytta "
            "mejl dit, eller ange en etikett (t.ex. \"Kvitton\" eller \"Labels/Kvitton\")."
        )
    if not key.startswith(LABEL_PREFIX.casefold()):
        name = LABEL_PREFIX + name
    if name == LABEL_PREFIX:
        raise ValueError("Etikettnamnet är tomt. Ange t.ex. \"Kvitton\" eller \"Labels/Kvitton\".")
    _check_user_folder(name)
    _quote_mailbox(name)
    return name


async def _require_label(imap: IMAPClient, label: str) -> None:
    """Kontrollerar med LIST att etiketten finns; annars ValueError med hänvisning till create_folder."""
    # "*" och "%" i namnet är jokertecken i LIST: bara exakt samma namn räknas
    if any(name == label for _, name in await imap._list(_quote_mailbox(label))):
        return
    raise ValueError(
        f"Etiketten {label} finns inte. Skapa den först med create_folder(\"{label}\"); "
        "list_mailboxes visar vilka etiketter som finns."
    )


def _parse_identities(lines: list) -> dict[str, dict[str, Any]]:
    """UID → {"message_id", "date", "size"} ur ett FETCH-svar med _IDENTITY_ITEMS.

    UID och övriga fält kan stå både före och efter header-literalen (Bridge
    lägger UID efter vid UID FETCH), och svaren kan komma i valfri ordning.
    """
    out: dict[str, dict[str, Any]] = {}
    i = 0
    while i < len(lines):
        head = lines[i]
        i += 1
        if isinstance(head, bytearray):
            continue
        head_s = _decode(head).strip()
        if not _FETCH_START_RE.match(head_s):
            continue
        raw = b""
        tail = ""
        if _LITERAL_END_RE.search(head_s):
            if i < len(lines) and isinstance(lines[i], bytearray):
                raw = bytes(lines[i])
                i += 1
            if i < len(lines) and not isinstance(lines[i], bytearray):
                candidate = _decode(lines[i]).strip()
                if not _FETCH_START_RE.match(candidate):
                    tail = candidate
                    i += 1
        meta = f"{_LITERAL_END_RE.sub('', head_s)} {tail}"
        uid_m = _UID_RE.search(meta)
        if not uid_m:
            continue
        date_m = _INTERNALDATE_RE.search(meta)
        size_m = _SIZE_RE.search(meta)
        message_id = BytesHeaderParser().parsebytes(raw).get("message-id") if raw else None
        out[uid_m.group(1)] = {
            "message_id": str(message_id).strip() if message_id else None,
            "date": date_m.group(1) if date_m else None,
            "size": size_m.group(1) if size_m else None,
        }
    return out


async def _fetch_identities_by_uid(imap: IMAPClient, mailbox: str, uids: list[str]) -> dict[str, dict]:
    resp = await imap._client.uid("fetch", uid_set(uids), _IDENTITY_ITEMS)
    _require_ok(resp, f"Hämtningen av Message-ID i {mailbox}")
    return _parse_identities(resp.lines)


async def _find_in_label(
    imap: IMAPClient, label: str, sources: dict[str, dict]
) -> tuple[dict[str, str], dict[str, str]]:
    """Hittar varje källmejls UID i etikettens vy (som måste vara vald).

    Söker med SEARCH HEADER Message-ID (Bridge matchar som delsträng) och
    jämför sedan exakt Message-ID, INTERNALDATE och storlek. Returnerar
    (käll-UID → etikett-UID, käll-UID → fel).
    """
    message_ids = sorted({info["message_id"] for info in sources.values()})
    seqnums: set[str] = set()
    for start in range(0, len(message_ids), _SEARCH_GROUP):
        group = message_ids[start:start + _SEARCH_GROUP]
        terms = [f"HEADER Message-ID {_imap_quoted(mid, 'Message-ID')}" for mid in group]
        criteria = ["OR"] * (len(terms) - 1) + terms
        seqnums.update(await imap._search_seqnums(criteria))

    candidates: dict[str, dict] = {}
    ordered = sorted(seqnums, key=int)
    for start in range(0, len(ordered), _FETCH_CHUNK_SIZE):
        chunk = ordered[start:start + _FETCH_CHUNK_SIZE]
        resp = await imap._client.fetch(",".join(chunk), _IDENTITY_ITEMS)
        _require_ok(resp, f"Hämtningen av sökträffarna i {label}")
        candidates.update(_parse_identities(resp.lines))

    found: dict[str, str] = {}
    errors: dict[str, str] = {}
    for src_uid, info in sources.items():
        same = [
            uid for uid, cand in candidates.items()
            if cand["message_id"] == info["message_id"]
            and cand["date"] == info["date"] and cand["size"] == info["size"]
        ]
        if not same:
            errors[src_uid] = f"Mejlet med UID {src_uid} har inte etiketten {label}."
        elif len(same) > 1:
            errors[src_uid] = (
                f"Det finns flera mejl i {label} som inte går att skilja från UID {src_uid} "
                f"(samma Message-ID, tid och storlek), så etiketten tas inte bort. "
                f"Lista {label} och ange UID:t där med mailbox=\"{label}\"."
            )
        else:
            found[src_uid] = same[0]
    return found, errors


async def _expunge_in_label(imap: IMAPClient, label: str, label_uids: list[str]) -> str | None:
    """Tar bort etiketten: UID STORE \\Deleted + UID EXPUNGE på just de UID:na i etikettens vy.

    Returnerar None om det lyckades, annars felet. Aldrig EXPUNGE utan UID.
    """
    uids = uid_set(sorted(set(label_uids), key=int))
    resp = await imap._uid("store", uids, "+FLAGS", r"(\Deleted)")
    if resp.result != "OK":
        return f"Borttagningen av etiketten {label} misslyckades ({resp.result}): {_response_text(resp)}"
    resp = await imap._uid("expunge", uids)
    if resp.result != "OK":
        # Lämna inte \Deleted kvar: nästa EXPUNGE i vyn skulle annars ta bort etiketten
        await imap._uid("store", uids, "-FLAGS", r"(\Deleted)")
        return f"Borttagningen av etiketten {label} misslyckades ({resp.result}): {_response_text(resp)}"
    return None


@_serialized
async def add_label(imap: IMAPClient, mailbox: str, uids: list[str], label: str) -> BulkResult:
    """Lägger till etiketten på mejlen med UID COPY; mejlen ligger kvar i mailbox."""
    uids = validate_uids(uids)
    target = label_mailbox(label)
    quoted_target = _quote_mailbox(target)
    _quote_mailbox(mailbox)
    if _mailbox_key(mailbox) == _mailbox_key(target):
        raise ValueError(
            f"Mejlen i {target} har redan etiketten {target}. Ange mappen där mejlet ligger "
            "(t.ex. INBOX) som mailbox."
        )
    await imap._ensure_connected()
    await _require_label(imap, target)
    await imap._select(mailbox)
    found, failed = await existing_uids(imap, mailbox, uids)
    ok: list[str] = []
    if found:
        resp = await imap._uid("copy", uid_set(found), quoted_target)
        if resp.result == "OK":
            ok = found
        else:
            failed += fail_all(
                found, f"Att lägga till etiketten {target} misslyckades ({resp.result}): {_response_text(resp)}"
            )
    return result(uids, ok, failed)


@_serialized
async def remove_label(imap: IMAPClient, mailbox: str, uids: list[str], label: str) -> BulkResult:
    """Tar bort etiketten från mejlen utan att flytta eller radera dem.

    Mejlets UID i etikettens vy hittas via Message-ID (UID:n gäller per vy);
    där görs UID STORE \\Deleted + UID EXPUNGE på just de UID:na, vilket hos
    Bridge bara tar bort etiketten. Är mailbox etiketten själv används UID:na direkt.
    """
    uids = validate_uids(uids)
    target = label_mailbox(label)
    _quote_mailbox(mailbox)
    await imap._ensure_connected()
    await _require_label(imap, target)

    if _mailbox_key(mailbox) == _mailbox_key(target):
        await imap._select(target)
        found, failed = await existing_uids(imap, target, uids)
        mapping = {uid: uid for uid in found}
    else:
        await imap._select(mailbox)
        identities = await _fetch_identities_by_uid(imap, mailbox, uids)
        failed = []
        sources: dict[str, dict] = {}
        for uid in uids:
            info = identities.get(uid)
            if info is None:
                failed.append({"uid": uid, "error": missing_error(uid, mailbox)})
            elif not info["message_id"]:
                failed.append({"uid": uid, "error": (
                    f"Mejlet med UID {uid} i {mailbox} saknar Message-ID och kan inte hittas i "
                    f"{target}. Lista {target} och ange UID:t där med mailbox=\"{target}\"."
                )})
            else:
                sources[uid] = info
        mapping = {}
        if sources:
            await imap._select(target)
            mapping, errors = await _find_in_label(imap, target, sources)
            failed += [{"uid": uid, "error": error} for uid, error in errors.items()]

    ok: list[str] = []
    if mapping:
        error = await _expunge_in_label(imap, target, list(mapping.values()))
        if error is None:
            ok = list(mapping)
        else:
            failed += fail_all(list(mapping), error)
    return result(uids, ok, failed)



@_serialized
async def set_starred(imap: IMAPClient, mailbox: str, uids: list[str], starred: bool) -> BulkResult:
    """Stjärnmärker (\\Flagged) eller avmarkerar mejlen; gäller i alla vyer hos Proton."""
    what = "Stjärnmärkningen" if starred else "Borttagningen av stjärnmärkningen"
    return await store_flags(imap, mailbox, uids, r"(\Flagged)", starred, what)

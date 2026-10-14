import asyncio
import functools
import logging
import math
import re
from datetime import datetime
from email.parser import BytesHeaderParser
from typing import Any

import aioimaplib

from .config import Settings
from .email_parser import decode_header_value
from .mailbox_names import decode_modified_utf7, describe_mailbox, encode_modified_utf7

logger = logging.getLogger(__name__)

# Format: (\Flags) "delimiter" "name"  eller  (\Flags) "delimiter" name;
# avgränsaren kan också vara NIL. Namnet är en quoted-string (RFC 3501) eller en atom.
_LIST_RE = re.compile(
    r'^\(([^)]*)\)\s+(?:"(?:[^"\\]|\\.)*"|NIL)\s+(?:"((?:[^"\\]|\\.)*)"|([^\s"]+))$',
    re.IGNORECASE,
)
_QUOTED_ESCAPE_RE = re.compile(r'\\(.)')
_UID_RE = re.compile(r'\bUID\s+(\d+)\b')
_FLAGS_RE = re.compile(r'FLAGS\s+\(([^)]*)\)')
_STATUS_NUM_RE = re.compile(r'(\w+)\s+(\d+)')
_VALID_UID_RE = re.compile(r'^\d+$')
# Bara kontrolltecken (CR, LF, NUL m.fl.) kan bryta ut ur en quoted-string.
# Backslash och citattecken escapas av _quote_mailbox; "%", "*" och ".." är
# giltiga namn hos Proton och har ingen särskild betydelse utanför LIST-mönster.
# Ensamma surrogater går inte att koda till modified UTF-7.
_VALID_MAILBOX_RE = re.compile(r'^[^\x00-\x1F\x7F\uD800-\uDFFF]{1,255}$')


def _validate_mailbox(name: str) -> str:
    if not _VALID_MAILBOX_RE.match(name):
        raise ValueError(f"Ogiltigt mailbox-namn: {name!r}")
    return name


def _to_imap_date(value: str) -> str:
    """Accepterar YYYY-MM-DD eller DD-Mon-YYYY, returnerar alltid DD-Mon-YYYY."""
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.strftime("%d-%b-%Y")
    except ValueError:
        return value  # Antag redan rätt format


def _validate_uid(uid: str) -> str:
    """Kastar ValueError om uid inte är ett rent heltal (förhindrar IMAP sequence-set-injektion)."""
    if not _VALID_UID_RE.match(uid):
        raise ValueError(f"Ogiltigt UID: {uid!r} — måste vara ett heltal")
    return uid


def _escape_imap_string(value: str) -> str:
    """Escapar dubbla citattecken och backslash i ett IMAP quoted-string (RFC 3501)."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _quote_mailbox(name: str) -> str:
    """Validerar, kodar och citerar ett läsbart mailbox-namn för IMAP.

    Namnet kodas till modified UTF-7 (RFC 3501 §5.1.3), så att "Labels/Näs"
    skickas som "Labels/N&AOQ-s", och citeras som quoted-string.

    Mailbox-namn som innehaller tecken utanfor IMAP:s "atom"-syntax (t.ex.
    hakparenteser eller mellanslag) maste skickas citerade, annars misslyckas
    SELECT/STATUS/CREATE/COPY/RENAME tyst eller med fel mot vissa IMAP-servrar.
    """
    _validate_mailbox(name)
    return f'"{_escape_imap_string(encode_modified_utf7(name))}"'


def _decode(b: bytes | bytearray | str) -> str:
    if isinstance(b, (bytes, bytearray)):
        return b.decode("utf-8", errors="replace")
    return b


def _response_text(resp) -> str:
    """Serverns förklaring i ett IMAP-svar, t.ex. "no such mailbox"."""
    return " ".join(_decode(line) for line in resp.lines).strip()


def _parse_seqnums(resp) -> list[str]:
    if resp.result != "OK" or not resp.lines:
        return []
    line = _decode(resp.lines[0]).strip()
    return [n for n in line.split() if n.isdigit()]


def _parse_list_line(line: str) -> str | None:
    """Extraherar det läsbara mappnamnet ur en IMAP LIST-rad. Returnerar None om raden inte matchar."""
    entry = _parse_list_entry(line)
    return entry[1] if entry else None


def _parse_list_entry(line: str) -> tuple[list[str], str] | None:
    """Extraherar attributen och det läsbara mappnamnet ur en IMAP LIST-rad.

    Namnet avescapas och avkodas från modified UTF-7, så att _quote_mailbox
    ger tillbaka exakt samma namn. Returnerar None om raden inte matchar.
    """
    line = line.strip()
    if not line or line.startswith("command"):
        return None
    m = _LIST_RE.match(line)
    if not m:
        return None
    attributes = m.group(1).split()
    if m.group(2) is not None:
        wire = _QUOTED_ESCAPE_RE.sub(r"\1", m.group(2))
    else:
        wire = m.group(3)
    try:
        return attributes, decode_modified_utf7(wire)
    except ValueError:
        logger.warning("Mappnamnet är inte giltig modified UTF-7, behålls oavkodat: %r", wire)
        return attributes, wire


def _parse_headers(raw: bytes) -> dict[str, str]:
    """Parsar raw RFC822-headers till en dict med lowercase-nycklar."""
    # BytesHeaderParser vecklar ut vikta rader (RFC 5322 §2.2.3); värdena
    # lämnas annars råa, eftersom get_email_headers används för analys
    result: dict[str, str] = {}
    for k, v in BytesHeaderParser().parsebytes(raw).items():
        result[k.lower()] = re.sub(r"\s*\r?\n\s*", " ", str(v)).strip()
    return result


def _serialized(method):
    """Kör IMAP-operationen under klientens lås.

    MCP-servern kan ta emot flera verktygsanrop samtidigt, men en IMAP-session
    har ett tillstånd (inloggad, vald mapp). Utan lås kan två anrop logga in
    samtidigt eller byta mapp åt varandra mitt i en FETCH.
    """
    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        async with self._lock:
            return await method(self, *args, **kwargs)
    return wrapper


class IMAPClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: aioimaplib.IMAP4 | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        logger.info("Ansluter till IMAP %s:%d (plain)", self._settings.imap_host, self._settings.imap_port)
        # Bridge v3 på port 1143 kräver plain IMAP (inte direkt SSL/TLS)
        self._client = aioimaplib.IMAP4(
            host=self._settings.imap_host,
            port=self._settings.imap_port,
        )
        await self._client.wait_hello_from_server()
        await self._client.login(self._settings.username, self._settings.password)
        logger.info("IMAP inloggad som %s", self._settings.username)

    async def disconnect(self) -> None:
        if self._client:
            try:
                await self._client.logout()
            except Exception:
                pass
            self._client = None

    async def _ensure_connected(self) -> None:
        if self._client is None:
            await self.connect()
            return
        try:
            await asyncio.wait_for(self._client.noop(), timeout=5.0)
        except Exception:
            logger.warning("IMAP NOOP misslyckades — återansluter")
            self._client = None
            await self.connect()

    @_serialized
    async def list_mailboxes(self) -> list[dict[str, Any]]:
        await self._ensure_connected()
        resp = await self._client.list('""', "*")
        mailboxes = []
        if resp.result == "OK":
            for line in resp.lines:
                entry = _parse_list_entry(_decode(line))
                if entry and entry[1]:
                    mailboxes.append(describe_mailbox(entry[1], entry[0]))
        return mailboxes

    @_serialized
    async def list_messages(
        self, mailbox: str, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        await self._ensure_connected()
        select_resp = await self._client.select(_quote_mailbox(mailbox))

        # Hämta EXISTS-räknaren från SELECT-svaret
        exists = 0
        for line in select_resp.lines:
            text = _decode(line)
            m = re.search(r'(\d+)\s+EXISTS', text)
            if m:
                exists = int(m.group(1))
                break

        if page < 1 or page_size < 1:
            raise ValueError(f"page och page_size måste vara >= 1 (fick page={page}, page_size={page_size})")

        total_pages = math.ceil(exists / page_size) if exists > 0 else 0

        # Beräkna sekvensintervall för nyaste-först paginering. En sida förbi
        # slutet är tom — annars skulle max(1, ...) nedan ge det äldsta brevet.
        offset = (page - 1) * page_size
        if offset >= exists:
            return {
                "messages": [],
                "total": exists,
                "page": page,
                "pages": total_pages,
                "has_more": False,
            }

        stop = exists - offset
        start = max(1, stop - page_size + 1)

        fetch_resp = await self._client.fetch(
            f"{start}:{stop}",
            "(UID FLAGS BODY.PEEK[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)])",
        )
        if fetch_resp.result != "OK":
            return {
                "messages": [],
                "total": exists,
                "page": page,
                "pages": total_pages,
                "has_more": page < total_pages,
            }

        msgs = _sort_newest_first(_parse_fetch_metadata(fetch_resp.lines))
        return {
            "messages": msgs,
            "total": exists,
            "page": page,
            "pages": total_pages,
            "has_more": page < total_pages,
        }

    @_serialized
    async def get_message(self, mailbox: str, uid: str) -> bytes | None:
        await self._ensure_connected()
        await self._client.select(_quote_mailbox(mailbox))
        resp = await self._client.uid("fetch", _validate_uid(uid), "BODY.PEEK[]")
        if resp.result != "OK":
            return None
        # lines[0] = "SEQNUM FETCH (BODY[] {SIZE}"
        # lines[1] = bytearray with raw email
        for line in resp.lines:
            if isinstance(line, bytearray) and len(line) > 10:
                return bytes(line)
        return None

    @_serialized
    async def search_messages(
        self,
        mailbox: str,
        from_addr: str | None = None,
        subject: str | None = None,
        since: str | None = None,
        before: str | None = None,
        unseen: bool | None = None,
        max_results: int = 200,
    ) -> list[dict]:
        await self._ensure_connected()
        await self._client.select(_quote_mailbox(mailbox))

        criteria: list[str] = []
        if from_addr:
            criteria += ["FROM", f'"{_escape_imap_string(from_addr)}"']
        if subject:
            criteria += ["SUBJECT", f'"{_escape_imap_string(subject)}"']
        if since:
            criteria += ["SINCE", _to_imap_date(since)]
        if before:
            criteria += ["BEFORE", _to_imap_date(before)]
        if unseen is True:
            criteria.append("UNSEEN")
        elif unseen is False:
            criteria.append("SEEN")
        if not criteria:
            criteria = ["ALL"]

        # search() returnerar sekvensnummer — vi hämtar sedan metadata
        resp = await self._client.search(" ".join(criteria))
        seqnums = _parse_seqnums(resp)
        if not seqnums:
            return []

        # Begränsa till nyaste max_results för att undvika rekursionsproblem
        seqnums = seqnums[-max_results:]

        fetch_resp = await self._client.fetch(
            ",".join(seqnums),
            "(UID FLAGS BODY.PEEK[HEADER.FIELDS (DATE FROM SUBJECT)])",
        )
        if fetch_resp.result != "OK":
            return []

        msgs = _sort_newest_first(_parse_fetch_metadata(fetch_resp.lines))
        return msgs

    @_serialized
    async def set_flags(self, mailbox: str, uid: str, flags: str, add: bool) -> bool:
        await self._ensure_connected()
        await self._client.select(_quote_mailbox(mailbox))
        action = "+FLAGS" if add else "-FLAGS"
        resp = await self._client.uid("store", _validate_uid(uid), action, flags)
        return resp.result == "OK"

    @_serialized
    async def move_message(self, mailbox: str, uid: str, target: str) -> bool:
        """Flyttar ett mejl med UID MOVE. Kastar ValueError om flytten avvisas eller misslyckas."""
        return await self._move(mailbox, uid, target)

    async def _move(self, mailbox: str, uid: str, target: str) -> bool:
        safe_uid = _validate_uid(uid)
        _quote_mailbox(mailbox)
        quoted_target = _quote_mailbox(target)
        _check_move(mailbox, target)
        await self._ensure_connected()
        await self._client.select(_quote_mailbox(mailbox))
        await self._require_uid(mailbox, safe_uid)
        resp = await self._client.uid("move", safe_uid, quoted_target)
        _require_ok(resp, f"Flytten av UID {safe_uid} från {mailbox} till {target}")
        return True

    @_serialized
    async def delete_message(self, mailbox: str, uid: str, permanent: bool = False) -> bool:
        """Flyttar ett mejl till Trash, eller raderar det permanent ur Trash/Drafts.

        Permanent radering görs med UID STORE \\Deleted + UID EXPUNGE på just
        det UID:t, aldrig med EXPUNGE på hela mappen.
        """
        safe_uid = _validate_uid(uid)
        key = _mailbox_key(mailbox)
        if not permanent:
            if key == "trash":
                raise ValueError(
                    "Mejlet ligger redan i Trash. Använd permanent=True för att radera det permanent."
                )
            return await self._move(mailbox, safe_uid, "Trash")

        if key not in _READD_DELETES:
            raise ValueError(
                f"Permanent radering görs bara i Trash eller Drafts, inte i {mailbox}. "
                "Ta bort mejlet utan permanent först, så hamnar det i Trash."
            )
        await self._ensure_connected()
        await self._client.select(_quote_mailbox(mailbox))
        await self._require_uid(mailbox, safe_uid)
        resp = await self._client.uid("store", safe_uid, "+FLAGS", r"(\Deleted)")
        _require_ok(resp, f"Borttagningsmarkeringen av UID {safe_uid} i {mailbox}")
        resp = await self._client.uid("expunge", safe_uid)
        if resp.result != "OK":
            # Lämna inte \Deleted kvar: nästa EXPUNGE i mappen skulle annars ta mejlet
            await self._client.uid("store", safe_uid, "-FLAGS", r"(\Deleted)")
        _require_ok(resp, f"Den permanenta raderingen av UID {safe_uid} i {mailbox}")
        return True

    async def _require_uid(self, mailbox: str, uid: str) -> None:
        """Kontrollerar att UID:t finns i den valda mappen.

        Bridge svarar OK på UID STORE/MOVE/EXPUNGE även för UID:n som inte
        finns, så utan kontrollen skulle verktygen rapportera lyckat för ingenting.
        """
        resp = await self._client.uid("fetch", uid, "(UID)")
        _require_ok(resp, f"Kontrollen av UID {uid} i {mailbox}")
        for line in resp.lines:
            m = _UID_RE.search(_decode(line))
            if m and int(m.group(1)) == int(uid):
                return
        raise ValueError(
            f"Inget meddelande med UID {uid} i {mailbox}. "
            "UID:n gäller per mapp — kontrollera att mailbox är samma mapp som UID:t kom från."
        )

    @_serialized
    async def get_message_headers(self, mailbox: str, uid: str) -> dict | None:
        await self._ensure_connected()
        await self._client.select(_quote_mailbox(mailbox))
        resp = await self._client.uid(
            "fetch", _validate_uid(uid),
            "BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE MESSAGE-ID REPLY-TO)]"
        )
        if resp.result != "OK":
            return None
        for line in resp.lines:
            if isinstance(line, bytearray) and len(line) > 4:
                return _parse_headers(bytes(line))
        return None

    @_serialized
    async def create_folder(self, name: str) -> bool:
        await self._ensure_connected()
        resp = await self._client.create(_quote_mailbox(name))
        return resp.result == "OK"

    @_serialized
    async def delete_folder(self, name: str) -> bool:
        await self._ensure_connected()
        resp = await self._client.delete(_quote_mailbox(name))
        return resp.result == "OK"

    @_serialized
    async def rename_folder(self, old_name: str, new_name: str) -> bool:
        await self._ensure_connected()
        resp = await self._client.rename(_quote_mailbox(old_name), _quote_mailbox(new_name))
        return resp.result == "OK"

    @_serialized
    async def get_mailbox_status(self, mailbox: str) -> dict[str, int]:
        await self._ensure_connected()
        resp = await self._client.status(_quote_mailbox(mailbox), "(MESSAGES UNSEEN)")
        status: dict[str, int] = {}
        if resp.result == "OK":
            for line in resp.lines:
                text = _decode(line)
                for m in _STATUS_NUM_RE.finditer(text):
                    key = m.group(1).lower()
                    if key in ("messages", "unseen"):
                        status[key] = int(m.group(2))
        return status


def _sort_newest_first(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sorterar på UID fallande. UID speglar ankomstordning i mappen, till
    skillnad från Date-headern som avsändaren själv sätter."""
    return sorted(msgs, key=lambda m: int(m["uid"]) if m["uid"].isdigit() else -1, reverse=True)


def _parse_fetch_metadata(lines: list) -> list[dict[str, Any]]:
    """Parsar FETCH-svar med UID, FLAGS och header-fält."""
    messages = []
    i = 0
    while i < len(lines):
        line_s = _decode(lines[i]).strip()

        if "FETCH" in line_s and "UID" in line_s:
            uid_m = _UID_RE.search(line_s)
            flags_m = _FLAGS_RE.search(line_s)
            uid = uid_m.group(1) if uid_m else ""
            flags = flags_m.group(1).split() if flags_m else []

            # Nästa rad kan vara header-data (bytearray)
            headers_raw = b""
            if i + 1 < len(lines) and isinstance(lines[i + 1], bytearray):
                headers_raw = bytes(lines[i + 1])
                i += 1

            # email-parsern hanterar vikta rader; decode_header_value avkodar
            # RFC 2047-ord (åäö, emoji) och slår ihop radbrytningar
            hdrs = BytesHeaderParser().parsebytes(headers_raw)

            messages.append({
                "uid": uid,
                "flags": flags,
                "subject": decode_header_value(hdrs.get("subject")),
                "from": decode_header_value(hdrs.get("from")),
                "to": decode_header_value(hdrs.get("to")),
                "date": decode_header_value(hdrs.get("date")),
                "message_id": decode_header_value(hdrs.get("message-id")),
            })
        i += 1
    return messages


def _require_ok(resp, what: str) -> None:
    if resp.result != "OK":
        raise ValueError(f"{what} misslyckades ({resp.result}): {_response_text(resp)}")


def _mailbox_key(name: str) -> str:
    return name.casefold()


def _is_label_view(name: str) -> bool:
    """Etiketter (Labels/…) och Starred: ett mejl där ligger också i någon mapp."""
    key = _mailbox_key(name)
    return key == "starred" or key.startswith("labels/")


# Mappar där Bridge raderar permanent när ett mejl som redan finns där läggs dit igen
_READD_DELETES = ("trash", "drafts")


def _check_move(source: str, target: str) -> None:
    """Avvisar flyttar som Bridge nekar eller som kan radera mejlet permanent."""
    src, dst = _mailbox_key(source), _mailbox_key(target)
    if src == dst:
        raise ValueError(
            f"Källa och mål är samma mapp ({source}). Bridge tar då först bort mejlet ur "
            "mappen och lägger sedan tillbaka det — i Trash och Drafts raderas det permanent."
        )
    if "all mail" in (src, dst):
        raise ValueError(
            "Bridge tillåter inte flytt till eller från All Mail. Ange mappen där mejlet "
            "ligger (t.ex. INBOX, Archive eller Folders/…) som källa."
        )
    if {src, dst} == {"inbox", "sent"}:
        raise ValueError("Bridge tillåter inte flytt mellan INBOX och Sent.")
    if dst in _READD_DELETES and _is_label_view(source):
        raise ValueError(
            f"Flytt till {target} från {source} avvisas: mejlet kan redan ligga i {target}, "
            "och då raderar Bridge det permanent. Ange mappen där mejlet ligger "
            "(t.ex. INBOX, Archive eller Folders/…) som källa."
        )

"""Read-only IMAP client for Proton Mail Bridge.

This fork can only read. Three independent layers enforce that:

1. There is no code here that changes a mailbox: no STORE, COPY, MOVE,
   EXPUNGE, APPEND, CREATE, DELETE or RENAME.
2. Mailboxes are opened with EXAMINE (read-only) instead of SELECT, and
   message bodies are fetched with BODY.PEEK so nothing is marked as read.
3. Every line sent to the server passes through ``_check_outgoing_line``,
   which refuses anything that is not a single command from
   ``_ALLOWED_COMMANDS``. A bug in argument handling therefore cannot turn
   into a write.
"""
import asyncio
import logging
import math
import re
from datetime import date
from typing import Any

import aioimaplib

from .config import Settings

logger = logging.getLogger(__name__)

# Format: (\Flags) "delimiter" "name"  or  (\Flags) "delimiter" name
_LIST_RE = re.compile(r'\([^)]*\)\s+"[^"]*"\s+(.+)$')
_UID_RE = re.compile(r'\bUID\s+(\d+)\b')
_FLAGS_RE = re.compile(r'FLAGS\s+\(([^)]*)\)')
_STATUS_NUM_RE = re.compile(r'(\w+)\s+(\d+)')

# All of these are used with fullmatch(): "$" would accept a trailing newline.
_VALID_UID_RE = re.compile(r'[0-9]{1,10}')
_VALID_MAILBOX_RE = re.compile(r'[^\x00-\x1F\x7F%*"\\]{1,255}')
_ISO_DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')
_IMAP_DATE_RE = re.compile(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})')
_CTL_RE = re.compile(r'[\x00-\x1F\x7F]')

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MAX_SEARCH_TEXT = 200
_MAX_PAGE_SIZE = 100

# The only IMAP commands this server will ever put on the wire.
_ALLOWED_COMMANDS = frozenset({
    "CAPABILITY", "LOGIN", "LOGOUT", "NOOP",
    "LIST", "STATUS", "EXAMINE", "SEARCH", "FETCH",
})


def _validate_mailbox(name: str) -> str:
    if not isinstance(name, str) or not _VALID_MAILBOX_RE.fullmatch(name) or ".." in name:
        raise ValueError(f"Invalid mailbox name: {name!r}")
    return name


def _validate_uid(uid: str) -> str:
    """Raise ValueError unless uid is a plain integer (no ranges, no extra text)."""
    if not isinstance(uid, str) or not _VALID_UID_RE.fullmatch(uid):
        raise ValueError(f"Invalid UID: {uid!r} (must be a whole number)")
    return uid


def _to_imap_date(value: str) -> str:
    """Accept YYYY-MM-DD or DD-Mon-YYYY and return DD-Mon-YYYY.

    Anything else is rejected. The result is built from parsed numbers, never
    copied from the input, so it cannot carry extra search keys or line breaks.
    """
    if not isinstance(value, str):
        raise ValueError("Invalid date (use YYYY-MM-DD)")
    try:
        m = _ISO_DATE_RE.fullmatch(value)
        if m:
            parsed = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        else:
            m = _IMAP_DATE_RE.fullmatch(value)
            if not m:
                raise ValueError
            month = _MONTHS.index(m.group(2).capitalize()) + 1
            parsed = date(int(m.group(3)), month, int(m.group(1)))
    except ValueError:
        raise ValueError(f"Invalid date: {value!r} (use YYYY-MM-DD)") from None
    return f"{parsed.day:02d}-{_MONTHS[parsed.month - 1]}-{parsed.year:04d}"


def _search_string(value: str, field: str) -> str:
    """Return value as an IMAP quoted string for a SEARCH key.

    Line breaks and other control characters are rejected outright: they are
    what let a search value turn into a second IMAP command.
    """
    if not isinstance(value, str) or _CTL_RE.search(value):
        raise ValueError(f"Invalid {field} filter: line breaks and control characters are not allowed")
    if len(value) > _MAX_SEARCH_TEXT:
        raise ValueError(f"Invalid {field} filter: longer than {_MAX_SEARCH_TEXT} characters")
    return '"' + _escape_imap_string(value) + '"'


def _escape_imap_string(value: str) -> str:
    """Escape backslash and double quote for an IMAP quoted string (RFC 3501)."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _check_outgoing_line(line: str) -> None:
    """Refuse anything that is not one single, read-only IMAP command.

    ``line`` is "<tag> [UID ]<COMMAND> [args]" without the trailing CRLF. The
    error messages never include the line itself, because for LOGIN it
    contains the password.
    """
    if _CTL_RE.search(line):
        raise ValueError("Refusing to send an IMAP command containing a line break or control character")
    parts = line.split(" ")
    name = parts[1] if len(parts) > 1 else ""
    if name.upper() == "UID":
        name = parts[2] if len(parts) > 2 else ""
    if name.upper() not in _ALLOWED_COMMANDS:
        raise ValueError(f"Refusing to send IMAP command {name[:20]!r}: this server is read-only")


def _install_readonly_guard(client: Any) -> None:
    """Route every outgoing command line of an aioimaplib client through the guard."""
    protocol = getattr(client, "protocol", None)
    original_send = getattr(protocol, "send", None)
    if not callable(original_send):
        # Fail closed if a future aioimaplib no longer has this single choke point.
        raise RuntimeError("Unsupported aioimaplib version: cannot install the read-only guard")

    def guarded_send(line: str, scrub: str | None = None) -> None:
        _check_outgoing_line(str(line))
        return original_send(line, scrub=scrub)

    protocol.send = guarded_send


def _decode(b: bytes | bytearray | str) -> str:
    if isinstance(b, (bytes, bytearray)):
        return b.decode("utf-8", errors="replace")
    return b


def _parse_seqnums(resp) -> list[str]:
    if resp.result != "OK" or not resp.lines:
        return []
    line = _decode(resp.lines[0]).strip()
    return [n for n in line.split() if n.isdigit()]


def _parse_list_line(line: str) -> str | None:
    """Extract the mailbox name from an IMAP LIST line, or None if it is not one."""
    line = line.strip()
    if not line or line.startswith("command"):
        return None
    m = _LIST_RE.match(line)
    if not m:
        return None
    return m.group(1).strip().strip('"')


def _parse_headers(raw: bytes) -> dict[str, str]:
    """Parse raw RFC822 headers into a dict with lowercase keys."""
    result: dict[str, str] = {}
    for hline in raw.decode("utf-8", errors="replace").splitlines():
        if ": " in hline:
            k, _, v = hline.partition(": ")
            result[k.lower()] = v.strip()
    return result


class IMAPClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._allowed: frozenset[str] | None = getattr(settings, "allowed_mailbox_set", None)
        self._client: aioimaplib.IMAP4 | None = None

    # -- access control -------------------------------------------------

    def _is_allowed(self, name: str) -> bool:
        if self._allowed is None:
            return True
        if name.upper() == "INBOX":  # INBOX is case-insensitive in IMAP
            return any(a.upper() == "INBOX" for a in self._allowed)
        return name in self._allowed

    def _mailbox(self, name: str) -> str:
        """Validate a mailbox name, apply the allow-list, return it IMAP-quoted."""
        _validate_mailbox(name)
        if not self._is_allowed(name):
            raise PermissionError(
                f"Mailbox {name!r} is not in PROTONMAIL_ALLOWED_MAILBOXES"
            )
        # Validation forbids '"' and '\', so plain quoting is safe. Quoting is
        # what makes names with spaces ("Folders/My Stuff") work.
        return f'"{name}"'

    # -- connection -----------------------------------------------------

    async def connect(self) -> None:
        logger.info("Connecting to IMAP %s:%d", self._settings.imap_host, self._settings.imap_port)
        # Bridge v3 on port 1143 speaks plain IMAP (not direct TLS); the host is
        # restricted to this computer in config.py.
        client = aioimaplib.IMAP4(
            host=self._settings.imap_host,
            port=self._settings.imap_port,
        )
        _install_readonly_guard(client)
        await client.wait_hello_from_server()
        resp = await client.login(self._settings.username, self._settings.password)
        if getattr(resp, "result", "OK") != "OK":
            raise ConnectionError("IMAP login was rejected; check the Bridge username and password")
        self._client = client
        logger.info("IMAP login succeeded")

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
            logger.warning("IMAP NOOP failed; reconnecting")
            self._client = None
            await self.connect()

    async def _open_readonly(self, mailbox: str):
        """Open a mailbox with EXAMINE, which the server treats as read-only."""
        quoted = self._mailbox(mailbox)
        await self._ensure_connected()
        resp = await self._client.examine(quoted)
        protocol = self._client.protocol
        if resp.result != "OK":
            # After a failed EXAMINE no mailbox is open; never fall through to
            # reading whichever mailbox was open before.
            protocol.state = "AUTH"
            raise LookupError(f"Could not open mailbox {mailbox!r}")
        # aioimaplib 2.0.x only moves to its SELECTED state on SELECT, and it
        # refuses FETCH/SEARCH in any other state. A mailbox is open, read-only.
        protocol.state = "SELECTED"
        return resp

    # -- read operations ------------------------------------------------

    async def list_mailboxes(self) -> list[dict[str, str]]:
        await self._ensure_connected()
        resp = await self._client.list('""', "*")
        mailboxes = []
        if resp.result == "OK":
            for line in resp.lines:
                name = _parse_list_line(_decode(line))
                if name and self._is_allowed(name):
                    mb_type = "label" if name.startswith("Labels/") else "folder"
                    mailboxes.append({"name": name, "type": mb_type})
        return mailboxes

    async def list_messages(
        self, mailbox: str, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        if not isinstance(page, int) or page < 1:
            raise ValueError("page must be 1 or greater")
        if not isinstance(page_size, int) or not 1 <= page_size <= _MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {_MAX_PAGE_SIZE}")

        examine_resp = await self._open_readonly(mailbox)

        # Read the EXISTS count from the EXAMINE response
        exists = 0
        for line in examine_resp.lines:
            m = re.search(r'(\d+)\s+EXISTS', _decode(line))
            if m:
                exists = int(m.group(1))
                break

        total_pages = math.ceil(exists / page_size) if exists > 0 else 0
        envelope = {
            "messages": [],
            "total": exists,
            "page": page,
            "pages": total_pages,
            "has_more": page < total_pages,
        }

        offset = (page - 1) * page_size
        if exists == 0 or offset >= exists:
            return envelope

        # Sequence range for newest-first paging
        stop = exists - offset
        start = max(1, stop - page_size + 1)

        fetch_resp = await self._client.fetch(
            f"{start}:{stop}",
            "(UID FLAGS BODY.PEEK[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)])",
        )
        if fetch_resp.result != "OK":
            return envelope

        msgs = _parse_fetch_metadata(fetch_resp.lines)
        msgs.reverse()  # newest first
        envelope["messages"] = msgs
        return envelope

    async def get_message(self, mailbox: str, uid: str) -> bytes | None:
        safe_uid = _validate_uid(uid)
        await self._open_readonly(mailbox)
        # BODY.PEEK[] (not BODY[]) so reading never sets the \Seen flag
        resp = await self._client.uid("fetch", safe_uid, "BODY.PEEK[]")
        if resp.result != "OK":
            return None
        # lines[0] = "SEQNUM FETCH (BODY[] {SIZE}"
        # lines[1] = bytearray with the raw email
        for line in resp.lines:
            if isinstance(line, bytearray) and len(line) > 10:
                return bytes(line)
        return None

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
        # Build and validate every search key before touching the server.
        criteria: list[str] = []
        if from_addr:
            criteria += ["FROM", _search_string(from_addr, "from_addr")]
        if subject:
            criteria += ["SUBJECT", _search_string(subject, "subject")]
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

        await self._open_readonly(mailbox)

        # search() returns sequence numbers; metadata is fetched afterwards
        resp = await self._client.search(" ".join(criteria))
        seqnums = _parse_seqnums(resp)
        if not seqnums:
            return []

        # Keep only the newest max_results
        seqnums = seqnums[-max_results:]

        fetch_resp = await self._client.fetch(
            ",".join(seqnums),
            "(UID FLAGS BODY.PEEK[HEADER.FIELDS (DATE FROM SUBJECT)])",
        )
        if fetch_resp.result != "OK":
            return []

        msgs = _parse_fetch_metadata(fetch_resp.lines)
        msgs.reverse()  # newest first
        return msgs

    async def get_message_headers(self, mailbox: str, uid: str) -> dict | None:
        safe_uid = _validate_uid(uid)
        await self._open_readonly(mailbox)
        resp = await self._client.uid(
            "fetch", safe_uid,
            "BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE MESSAGE-ID REPLY-TO)]"
        )
        if resp.result != "OK":
            return None
        for line in resp.lines:
            if isinstance(line, bytearray) and len(line) > 4:
                return _parse_headers(bytes(line))
        return None

    async def get_mailbox_status(self, mailbox: str) -> dict[str, int]:
        quoted = self._mailbox(mailbox)
        await self._ensure_connected()
        resp = await self._client.status(quoted, "(MESSAGES UNSEEN)")
        status: dict[str, int] = {}
        if resp.result == "OK":
            for line in resp.lines:
                text = _decode(line)
                for m in _STATUS_NUM_RE.finditer(text):
                    key = m.group(1).lower()
                    if key in ("messages", "unseen"):
                        status[key] = int(m.group(2))
        return status


def _parse_fetch_metadata(lines: list) -> list[dict[str, Any]]:
    """Parse a FETCH response containing UID, FLAGS and header fields."""
    messages = []
    i = 0
    while i < len(lines):
        line_s = _decode(lines[i]).strip()

        if "FETCH" in line_s and "UID" in line_s:
            uid_m = _UID_RE.search(line_s)
            flags_m = _FLAGS_RE.search(line_s)
            uid = uid_m.group(1) if uid_m else ""
            flags = flags_m.group(1).split() if flags_m else []

            # The next line may be the header data (bytearray)
            headers_raw = b""
            if i + 1 < len(lines) and isinstance(lines[i + 1], bytearray):
                headers_raw = bytes(lines[i + 1])
                i += 1

            header_dict = _parse_headers(headers_raw)

            messages.append({
                "uid": uid,
                "flags": flags,
                "subject": header_dict.get("subject", ""),
                "from": header_dict.get("from", ""),
                "to": header_dict.get("to", ""),
                "date": header_dict.get("date", ""),
                "message_id": header_dict.get("message-id", ""),
            })
        i += 1
    return messages

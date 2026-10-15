"""Bevakning av nya mejl med IMAP IDLE (RFC 2177).

MailWatcher håller en EGEN anslutning till Bridge per bevakad mapp
(PROTONMAIL_WATCH_MAILBOXES, högst fem). En anslutning i IDLE är upptagen och
kan inte köra andra kommandon, så verktygens delade IMAPClient (med lås)
används aldrig här. Varje anslutning är en egen IMAPClient, så inloggning,
timeout, felmeddelanden och _BridgeProtocol är desamma som för verktygen.

Per mapp, i en bakgrundsuppgift:
1. Logga in och välj mappen. Första gången blir UIDNEXT - 1 vattenmärket:
   mejl som redan fanns räknas inte som nya.
2. IDLE. Bridge (liksom RFC 2177) kopplar ner en IDLE efter 29 minuter, så
   den avslutas med DONE och startas om var DEFAULT_RENEW_SECONDS.
3. Efter varje IDLE-omgång (EXISTS/RECENT eller förnyelse): DONE, UID SEARCH
   efter UID:n över vattenmärket och hämta deras metadata med BODY.PEEK
   (inget markeras som läst), med samma parser som list_emails. Lägg dem i
   händelsekön och anropa lyssnarna. Tillbaka till 2.
   Bridge skickar köade uppdateringar i svaret på nästa kommando och aldrig
   igen: en EXISTS i svaret på UID SEARCH/FETCH (som aioimaplib annars
   kastar) eller i IDLE-kön för den omgång som avslutas räknas därför som
   "ett nytt mejl kan ha kommit", och sökningen görs om innan nästa IDLE.
4. Bryts anslutningen (Bridge startas om) görs ett nytt försök efter
   BACKOFF_INITIAL sekunder, sedan dubbelt så länge upp till BACKOFF_MAX.
   Väntetiden börjar om först när en IDLE-omgång har gått klart: nekar
   Bridge IDLE eller bryter den direkt växer den ändå. Mappen räknas som
   bevakad (is_watching) först när Bridge har bekräftat IDLE.
   Vid återanslutning hämtas det som kom under avbrottet. Har UIDVALIDITY
   ändrats gäller inte de gamla UID:na: vattenmärket och kön nollställs och
   UIDNEXT - 1 blir nytt vattenmärke.

Ingenting här får krascha servern: fel loggas (till stderr) och leder till
ett nytt försök. start() väntar inte på Bridge.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from aioimaplib.aioimaplib import STOP_WAIT_SERVER_PUSH, Abort

from .config import Settings
from .imap_client import (
    _FETCH_CHUNK_SIZE,
    _METADATA_ITEMS,
    IMAPClient,
    _BridgeProtocol,
    _close_transport,
    _decode,
    _exists,
    _parse_fetch_metadata,
    _parse_seqnums,
    _quote_mailbox,
    _require_ok,
    _response_text,
    _serialized,
    _sort_newest_first,
)

logger = logging.getLogger(__name__)

# Bridge kopplar ner en IDLE efter 29 minuter; förnya god tid före
DEFAULT_RENEW_SECONDS = 25 * 60
_IDLE_LIMIT_SECONDS = 29 * 60
BACKOFF_INITIAL = 1.0
BACKOFF_MAX = 300.0
# Händelsekö per mapp (de senaste nya mejlen)
QUEUE_SIZE = 200
# Högst så många nya mejl hämtas per omgång; fler (t.ex. efter ett långt
# avbrott) ger bara de nyaste i kön, och verktygen frågar då Bridge själva
FETCH_LIMIT = 200
# Högst så många sökningar efter en IDLE-omgång när Bridge hela tiden
# rapporterar nya mejl i svaren; resten fångas av nästa omgång
CATCH_UP_ROUNDS = 5

_UIDVALIDITY_RE = re.compile(r"\[UIDVALIDITY\s+(\d+)\]", re.IGNORECASE)
_UIDNEXT_RE = re.compile(r"\[UIDNEXT\s+(\d+)\]", re.IGNORECASE)
_PUSH_RE = re.compile(r"^(?:\*\s+)?\d+\s+(?:EXISTS|RECENT)\b", re.IGNORECASE)
_UID_ITEM_RE = re.compile(r"\bUID\s+(\d+)", re.IGNORECASE)
# Bridges svar på UID SEARCH UID n:* i en mapp utan mejl (i stället för OK)
_NO_SUCH_MESSAGE_RE = re.compile(r"\bno such message\b", re.IGNORECASE)

Listener = Callable[[str, list[dict[str, Any]]], Awaitable[None]]


def mailbox_key(name: str) -> str:
    """INBOX jämförs utan hänsyn till skiftläge (RFC 3501), övriga namn exakt."""
    return "INBOX" if name.upper() == "INBOX" else name


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class MailboxInfo:
    uidvalidity: int | None
    uidnext: int | None
    exists: int


def _parse_select(resp) -> MailboxInfo:
    uidvalidity = uidnext = None
    for line in resp.lines:
        if isinstance(line, bytearray):
            continue
        text = _decode(line)
        if m := _UIDVALIDITY_RE.search(text):
            uidvalidity = int(m.group(1))
        if m := _UIDNEXT_RE.search(text):
            uidnext = int(m.group(1))
    return MailboxInfo(uidvalidity=uidvalidity, uidnext=uidnext, exists=_exists(resp) or 0)


def _is_new_mail_push(lines) -> bool:
    return any(_PUSH_RE.match(_decode(line).strip()) for line in lines if not isinstance(line, bytearray))


class _WatchProtocol(_BridgeProtocol):
    """_BridgeProtocol som märker EXISTS/RECENT utanför SELECT och IDLE.

    Bridge skickar köade uppdateringar i svaret på nästa kommando (gluon,
    internal/session/handle.go), även UID SEARCH och FETCH. aioimaplib har
    ingen mottagare för dem där och kastar raden. saw_push sätts då, så att
    bevakningen söker en gång till i stället för att tappa mejlet.
    """

    saw_push = False

    def _untagged_response(self, line: bytes):
        if self.pending_sync_command is None and _PUSH_RE.match(_decode(line).strip()):
            self.saw_push = True
        return super()._untagged_response(line)


def _watch_pushes(client) -> None:
    """Låter bevakningens anslutning använda _WatchProtocol (attrapper lämnas)."""
    protocol = getattr(client, "protocol", None)
    if type(protocol) is _BridgeProtocol:
        protocol.__class__ = _WatchProtocol


async def select_info(imap: IMAPClient, mailbox: str) -> MailboxInfo:
    """SELECT mailbox (med klientens kontroller) och läs UIDVALIDITY/UIDNEXT.

    Saknas UIDNEXT i svaret räknas det fram ur det högsta UID:t.
    """
    info = _parse_select(await imap._select(mailbox))
    if info.uidnext is None:
        highest = 0
        if info.exists:
            resp = await imap._uid("fetch", "*", "(UID)")
            _require_ok(resp, f"Hämtningen av högsta UID i {mailbox}")
            uids = [int(m.group(1)) for line in resp.lines if not isinstance(line, bytearray)
                    for m in _UID_ITEM_RE.finditer(_decode(line))]
            highest = max(uids, default=0)
        info = MailboxInfo(info.uidvalidity, highest + 1, info.exists)
    return info


async def new_uids(imap: IMAPClient, after: int) -> list[int]:
    """UID:n över after i vald mapp, stigande.

    "n:*" ger enligt RFC 3501 alltid minst det sista mejlet, även när dess
    UID är lägre än n, därför filtreras svaret. I en tom mapp svarar Bridge
    "NO no such message" i stället för ett tomt svar; det betyder inga mejl.
    """
    resp = await imap._client.uid_search("UID", f"{after + 1}:*")
    if resp.result == "NO" and _NO_SUCH_MESSAGE_RE.search(_response_text(resp)):
        return []
    _require_ok(resp, "Sökningen efter nya mejl")
    # aioimaplib tar bort "* SEARCH": första raden är bara UID:na
    return sorted({u for u in map(int, _parse_seqnums(resp)) if u > after})


async def fetch_metadata(imap: IMAPClient, mailbox: str, uids: list[int]) -> list[dict[str, Any]]:
    """Metadata (som list_emails) för uids i vald mapp, nyaste först.

    BODY.PEEK via _METADATA_ITEMS: inget markeras som läst.
    """
    wanted = {str(u) for u in uids}
    msgs: list[dict[str, Any]] = []
    for start in range(0, len(uids), _FETCH_CHUNK_SIZE):
        chunk = uids[start:start + _FETCH_CHUNK_SIZE]
        resp = await imap._uid("fetch", ",".join(map(str, chunk)), _METADATA_ITEMS)
        _require_ok(resp, f"Hämtningen av nya mejl i {mailbox}")
        msgs += [m for m in _parse_fetch_metadata(resp.lines) if m["uid"] in wanted]
    return [{**m, "mailbox": mailbox} for m in _sort_newest_first(msgs)]


@_serialized
async def poll_new_messages(
    imap: IMAPClient, mailbox: str, after: int | None, uidvalidity: int | None, limit: int
) -> dict[str, Any]:
    """Nya mejl via verktygens delade anslutning (när bevakningen inte kan svara).

    after=None, eller ett annat UIDVALIDITY än det angivna, ger inga mejl men
    ett nytt vattenmärke (UIDNEXT - 1). Annars de äldsta `limit` mejlen över
    after (så att vattenmärket kan flyttas fram utan luckor), nyaste först.

    Ligger after förbi det senaste mejlet (UIDNEXT - 1) blir last_uid
    UIDNEXT - 1 och clamped True: ett vattenmärke får aldrig peka förbi
    riktiga mejl.

    Returnerar dict med messages, uidvalidity, last_uid (nytt vattenmärke),
    has_more, reset (True om UIDVALIDITY ändrats) och clamped.
    """
    _quote_mailbox(mailbox)
    await imap._ensure_connected()
    info = await select_info(imap, mailbox)
    newest = info.uidnext - 1
    reset = uidvalidity is not None and info.uidvalidity != uidvalidity
    if after is None or reset or after > newest:
        return {"messages": [], "uidvalidity": info.uidvalidity, "last_uid": newest,
                "has_more": False, "reset": reset, "clamped": after is not None and not reset}
    # En tom mapp söks inte alls (Bridge svarar NO på sökningen där)
    uids = await new_uids(imap, after) if info.exists else []
    taken = uids[:limit]
    msgs = await fetch_metadata(imap, mailbox, taken) if taken else []
    return {"messages": msgs, "uidvalidity": info.uidvalidity, "last_uid": taken[-1] if taken else after,
            "has_more": len(uids) > len(taken), "reset": False, "clamped": False}


@dataclass
class _MailboxState:
    name: str
    queue_size: int
    events: deque = field(init=False)
    uidvalidity: int | None = None
    # Högsta UID som bevakningen har sett
    watermark: int | None = None
    # Vattenmärket när bevakningen startade (eller UIDVALIDITY ändrades)
    baseline: int | None = None
    # Kön innehåller alla nya mejl med UID över floor
    floor: int | None = None
    connected: bool = False
    last_event: str | None = None
    last_error: str | None = None
    signal: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self.events = deque(maxlen=self.queue_size)


class MailWatcher:
    """Bevakar mappar med IDLE i egna anslutningar; se moduldokumentationen."""

    def __init__(
        self,
        settings: Settings,
        *,
        renew_seconds: float = DEFAULT_RENEW_SECONDS,
        backoff_initial: float = BACKOFF_INITIAL,
        backoff_max: float = BACKOFF_MAX,
        queue_size: int = QUEUE_SIZE,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not 0 < renew_seconds < _IDLE_LIMIT_SECONDS:
            raise ValueError("IDLE måste förnyas inom 29 minuter (Bridge kopplar ner den då)")
        self._settings = settings
        self.enabled = settings.watch_enabled
        self.mailboxes = settings.watch_mailbox_list
        self._renew = renew_seconds
        self._backoff_initial = backoff_initial
        self._backoff_max = backoff_max
        self._sleep = sleep
        self._states = {mailbox_key(m): _MailboxState(m, queue_size) for m in self.mailboxes}
        self._listeners: list[Listener] = []
        self._tasks: dict[str, asyncio.Task] = {}
        self._stopping = False
        # Verktygens vattenmärken per mapp: (UIDVALIDITY, UID). Här i stället
        # för i verktygsmodulen så att de lever lika länge som sessionen.
        self.marks: dict[str, tuple[int | None, int]] = {}

    # --- Livscykel ------------------------------------------------------------

    def start(self) -> None:
        """Starta en bakgrundsuppgift per mapp. Väntar inte på Bridge."""
        if not self.enabled:
            logger.info("Bevakningen av nya mejl är avstängd (PROTONMAIL_WATCH_ENABLED=false)")
            return
        self._stopping = False
        for key, state in self._states.items():
            if key not in self._tasks:
                self._tasks[key] = asyncio.create_task(
                    self._run(state), name=f"protonmail-watch:{state.name}"
                )

    async def stop(self) -> None:
        """Stoppa alla uppgifter och stäng anslutningarna. Kan anropas flera gånger."""
        self._stopping = True
        pending, self._tasks = set(self._tasks.values()), {}
        # Avbryt tills uppgiften verkligen är klar: asyncio.wait_for i Python
        # 3.10–3.11 kan svälja en avbrytning som sammanfaller med att det den
        # väntar på blir klart, och då skulle uppgiften gå vidare in i nästa IDLE.
        while pending:
            for task in pending:
                task.cancel()
            done, pending = await asyncio.wait(pending, timeout=0.5)
            for task in done:
                if not task.cancelled() and task.exception() is not None:
                    logger.warning("Bevakningen avslutades med fel: %s", task.exception())
        for state in self._states.values():
            state.connected = False
            self._wake(state)

    # --- Lyssnare och status --------------------------------------------------

    def add_listener(self, callback: Listener) -> None:
        """callback(mailbox, messages) anropas (await) för varje omgång nya mejl.

        Den körs i bevakningsuppgiften, så den bör vara snabb. Fel loggas och
        stoppar varken bevakningen eller andra lyssnare.
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: Listener) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _state(self, mailbox: str) -> _MailboxState | None:
        return self._states.get(mailbox_key(mailbox))

    def is_watching(self, mailbox: str) -> bool:
        """True om mappen bevakas och anslutningen är uppe just nu."""
        state = self._state(mailbox)
        return bool(self.enabled and state is not None and state.connected and not self._stopping)

    def status(self, mailbox: str) -> dict[str, Any]:
        state = self._state(mailbox)
        return {
            "watching": self.is_watching(mailbox),
            "last_event": state.last_event if state else None,
            "last_error": state.last_error if state else None,
        }

    def recent_events(self, mailbox: str) -> list[dict[str, Any]]:
        """Händelsekön för mappen, nyaste först."""
        state = self._state(mailbox)
        return list(reversed(state.events)) if state else []

    def uidvalidity(self, mailbox: str) -> int | None:
        """UIDVALIDITY som bevakningen senast såg för mappen, eller None."""
        state = self._state(mailbox)
        return state.uidvalidity if state else None

    def baseline(self, mailbox: str) -> tuple[int | None, int] | None:
        """(UIDVALIDITY, vattenmärke) när bevakningen av mappen började, eller None."""
        state = self._state(mailbox)
        if state is None or state.baseline is None:
            return None
        return state.uidvalidity, state.baseline

    def messages_since(self, mailbox: str, after: int, uidvalidity: int | None) -> list[dict[str, Any]] | None:
        """Mejl i kön med UID över after, nyaste först.

        None om kön inte kan svara säkert: mappen bevakas inte, after är
        äldre än kön eller högre än något UID bevakningen har sett, eller
        UIDVALIDITY är ett annat.
        """
        state = self._state(mailbox)
        if (not self.enabled or state is None or state.floor is None
                or state.uidvalidity != uidvalidity or not state.floor <= after <= state.watermark):
            return None
        return [m for m in reversed(state.events) if int(m["uid"]) > after]

    async def wait_for_messages(
        self, mailbox: str, after: int, uidvalidity: int | None, timeout: float
    ) -> list[dict[str, Any]] | None:
        """Vänta tills kön har mejl över after, högst timeout sekunder.

        Tom lista om tiden gick ut (eller bevakningen stoppades), None om kön
        inte kan svara (se messages_since). Inga IMAP-kommandon skickas.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            msgs = self.messages_since(mailbox, after, uidvalidity)
            if msgs is None or msgs or self._stopping:
                return msgs if msgs is not None else None
            remaining = deadline - loop.time()
            if remaining <= 0:
                return []
            try:
                await asyncio.wait_for(self._state(mailbox).signal.wait(), remaining)
            except asyncio.TimeoutError:
                return self.messages_since(mailbox, after, uidvalidity) or []

    # --- Händelser --------------------------------------------------------------

    @staticmethod
    def _wake(state: _MailboxState) -> None:
        signal, state.signal = state.signal, asyncio.Event()
        signal.set()

    def _record(self, state: _MailboxState, msgs: list[dict[str, Any]]) -> None:
        """Lägg nya mejl (nyaste först) i kön och väck väntande anrop."""
        for msg in reversed(msgs):  # äldst först in i kön
            if len(state.events) == state.events.maxlen:
                state.floor = max(state.floor or 0, int(state.events[0]["uid"]))
            state.events.append(msg)
            state.watermark = max(state.watermark or 0, int(msg["uid"]))
        state.last_event = _now()
        self._wake(state)

    async def _notify(self, mailbox: str, msgs: list[dict[str, Any]]) -> None:
        for callback in list(self._listeners):
            try:
                await callback(mailbox, msgs)
            except Exception:  # noqa: BLE001 — en lyssnare får inte stoppa bevakningen
                logger.exception("En lyssnare på nya mejl i %s misslyckades", mailbox)

    # --- Bevakningsuppgiften --------------------------------------------------

    async def _run(self, state: _MailboxState) -> None:
        delay = self._backoff_initial
        # Senast loggade fel; samma fel om och om igen loggas bara första gången
        logged_error: str | None = None
        while not self._stopping:
            imap = IMAPClient(self._settings)
            client = None
            try:
                await imap.connect()
                client = imap._client
                _watch_pushes(client)
                if "IDLE" not in getattr(client.protocol, "capabilities", ()):
                    raise ConnectionError("ProtonMail Bridge stöder inte IDLE")
                info = await select_info(imap, state.name)
                await self._sync(state, imap, info)
                logger.info("Bevakar %s efter nya mejl (IDLE)", state.name)
                while not self._stopping:
                    await self._idle(imap, client, state)
                    if self._stopping:
                        break
                    await self._catch_up(state, imap, client)
                    # En hel omgång gick klart: nästa avbrott är ett nytt fel
                    delay, logged_error = self._backoff_initial, None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — bevakningen får aldrig krascha servern
                error = str(exc) or type(exc).__name__
                # Samma fel om och om igen (Bridge nere) loggas bara första gången
                log = logger.warning if error != logged_error else logger.debug
                state.last_error = logged_error = error
                log("Bevakningen av %s avbröts: %s — nytt försök om %g s", state.name, error, delay)
            finally:
                state.connected = False
                _shutdown(imap, client)
            if self._stopping:
                break
            await self._sleep(delay)
            delay = min(delay * 2, self._backoff_max)

    async def _sync(self, state: _MailboxState, imap: IMAPClient, info: MailboxInfo) -> None:
        """Efter (åter)anslutning: sätt vattenmärket eller hämta det som kommit."""
        if state.uidvalidity is not None and info.uidvalidity != state.uidvalidity:
            logger.warning(
                "UIDVALIDITY för %s ändrades (%s → %s): de gamla UID:na gäller inte, "
                "vattenmärket nollställs", state.name, state.uidvalidity, info.uidvalidity,
            )
            state.watermark = None
            state.events.clear()
            self.marks.pop(mailbox_key(state.name), None)
        state.uidvalidity = info.uidvalidity
        if state.watermark is None:
            state.watermark = state.baseline = state.floor = info.uidnext - 1
        elif info.exists:  # en tom mapp har inget nytt (och Bridge svarar NO på sökningen)
            await self._fetch_new(state, imap)

    async def _catch_up(self, state: _MailboxState, imap: IMAPClient, client) -> None:
        """Hämta nya mejl efter en IDLE-omgång, tills inget tyder på fler.

        Görs efter varje omgång, även förnyelsen: en EXISTS mellan DONE och
        OK ligger i IDLE-kön och kommer aldrig igen. Rapporterar Bridge ett
        nytt mejl i svaret på sökningen eller hämtningen (saw_push), söks det
        igen, högst CATCH_UP_ROUNDS gånger.
        """
        protocol = getattr(client, "protocol", None)
        for _ in range(CATCH_UP_ROUNDS):
            if protocol is not None:
                protocol.saw_push = False
            _drain(client)  # täcks av sökningen nedan
            await self._fetch_new(state, imap)
            if not (getattr(protocol, "saw_push", False) is True or _drain(client)):
                return

    async def _fetch_new(self, state: _MailboxState, imap: IMAPClient) -> None:
        uids = await new_uids(imap, state.watermark)
        if not uids:
            return
        if len(uids) > FETCH_LIMIT:
            uids = uids[-FETCH_LIMIT:]
            state.floor = max(state.floor or 0, uids[0] - 1)
        msgs = await fetch_metadata(imap, state.name, uids)
        state.watermark = uids[-1]
        self._record(state, msgs)
        logger.info("%d nytt/nya mejl i %s", len(msgs), state.name)
        await self._notify(state.name, msgs)

    async def _idle(self, imap: IMAPClient, client, state: _MailboxState | None = None) -> bool:
        """En IDLE-omgång. True vid nytt mejl, False när den ska förnyas.

        När Bridge har bekräftat IDLE räknas state som ansluten. Kastar om
        anslutningen bryts, Bridge nekar IDLE eller inte svarar.
        """
        if self._stopping:
            return False
        if _drain(client):
            return True  # ett mejl som ingen har hämtat än: sök innan IDLE
        try:
            idle = await asyncio.wait_for(client.idle_start(timeout=self._renew), imap.timeout)
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(
                f"ProtonMail Bridge bekräftade inte IDLE inom {imap.timeout:g} s"
            ) from None
        except Abort:
            raise ConnectionError("ProtonMail Bridge nekade IDLE") from None
        if state is not None:
            state.connected, state.last_error = True, None
        new_mail = False
        push = None
        try:
            while True:
                push = asyncio.ensure_future(client.wait_server_push(timeout=self._renew + imap.timeout))
                done, _ = await asyncio.wait({push, idle}, return_when=asyncio.FIRST_COMPLETED)
                if push not in done:
                    idle.result()  # ConnectionError om anslutningen bröts
                    raise ConnectionError("ProtonMail Bridge avslutade IDLE")
                lines = push.result()
                if lines == STOP_WAIT_SERVER_PUSH:
                    break  # dags att förnya
                if _is_new_mail_push(lines):
                    new_mail = True
                    break
        finally:
            if push is not None and not push.done():
                push.cancel()
        if client.has_pending_idle():
            client.idle_done()
            try:
                await asyncio.wait_for(idle, imap.timeout)
            except asyncio.TimeoutError:
                raise asyncio.TimeoutError(
                    f"ProtonMail Bridge avslutade inte IDLE inom {imap.timeout:g} s"
                ) from None
        return new_mail


def _drain(client) -> bool:
    """Töm IDLE-kön (t.ex. en försenad förnyelsesignal). True om den hade EXISTS/RECENT."""
    queue = client.protocol.idle_queue
    pushed = False
    while not queue.empty():
        lines = queue.get_nowait()
        if lines != STOP_WAIT_SERVER_PUSH and _is_new_mail_push(lines):
            pushed = True
    return pushed


def _shutdown(imap: IMAPClient, client) -> None:
    """Stäng anslutningen och aioimaplib:s egna uppgifter (inga lösa tasks)."""
    if client is not None:
        waiter = getattr(client, "_idle_waiter", None)
        if waiter is not None:
            waiter.cancel()
        for task in list(getattr(client, "tasks", ())):
            task.cancel()
        _close_transport(client)
    imap._discard_connection()

"""Prenumerationer på resurser (resources/subscribe och notifications/resources/updated).

Klienten prenumererar på en resurs-URI (se resources.py); när resursen ändras
anropar servern notify_resource_updated(uri), och varje session som
prenumererar på den får notisen.

När skickas notiser:
- Nya mejl i en bevakad mapp (PROTONMAIL_WATCH_MAILBOXES, standard INBOX):
  bevakaren (imap_idle.py) meddelar mailbox://mappen.
- Efter ett lyckat skrivverktyg i den här servern: TOOL_CHANGES säger vilka
  resurser varje verktyg ändrar (källmapp, målmapp, mejlet, mapplistan,
  Drafts, Sent, Trash). Kroken sitter i verktygsomslutningen
  (tools/__init__.py, notify_after) och skickar i bakgrunden (notify_soon),
  så att verktygssvaret aldrig väntar på notiserna.
Ändringar som andra klienter gör (Proton-appen, webben, en annan IMAP-klient)
syns bara som nya mejl i bevakade mappar; flaggor, flyttar och mappändringar
utifrån ger ingen notis. En prenumeration godtas ändå på alla giltiga
resurser, eftersom serverns egna verktyg kan ändra var och en av dem. URI:er jämförs i kanonisk form
(resources.canonical_uri), så "mailbox://Folders/A/B" och
"mailbox://Folders%2FA%2FB" är samma resurs. Notisen skickas med den URI som
sessionen själv prenumererade med, så att klienten känner igen den.

En session glöms när den stängs (via sessionens exit-stack), när en notis
till den visar att anslutningen är stängd, och när MAX_CONSECUTIVE_TIMEOUTS
notiser i rad har tagit längre tid än SEND_TIMEOUT_SECONDS (en klient som
slutat läsa skulle annars få varje ny notis att vänta ut hela tidsgränsen,
för alltid). En lyckad notis nollställer räkningen. Notiserna skickas
parallellt med en tidsgräns per session: ett fel eller en hängande session
stoppar inte de andra.

FastMCP:s lågnivåserver annonserar alltid resources.subscribe=False; register()
skriver över det, eftersom servern nu hanterar prenumerationer.
"""
import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Any

import anyio
from pydantic import AnyUrl

from .resources import MAILBOXES_URI, canonical_uri, email_uri, mailbox_uri

logger = logging.getLogger(__name__)

# Tidsgräns för en notis till en session
SEND_TIMEOUT_SECONDS = 5.0
# Så många tidsgränser i rad innan sessionens prenumerationer tas bort
MAX_CONSECUTIVE_TIMEOUTS = 3


class SubscriptionRegistry:
    """Vilka sessioner som prenumererar på vilka resurser."""

    def __init__(self) -> None:
        # kanonisk URI → session → URI:n som sessionen prenumererade med
        self._subscriptions: dict[str, dict[Any, str]] = {}
        self._hooked: set[int] = set()
        # id(session) → antal notiser i rad som inte hunnit skickas
        self._timeouts: dict[int, int] = {}

    def subscribe(self, session: Any, uri: str) -> None:
        """Lägg till en prenumeration. ValueError om URI:n inte är en av serverns resurser."""
        key = canonical_uri(uri)
        self._subscriptions.setdefault(key, {})[session] = uri
        self._forget_on_exit(session)

    def unsubscribe(self, session: Any, uri: str) -> None:
        """Ta bort en prenumeration (ingenting händer om den inte finns)."""
        try:
            key = canonical_uri(uri)
        except ValueError:
            key = uri
        subscribers = self._subscriptions.get(key)
        if subscribers is not None:
            subscribers.pop(session, None)
            if not subscribers:
                del self._subscriptions[key]

    def forget(self, session: Any) -> None:
        """Ta bort alla prenumerationer för en session (t.ex. när den stängts)."""
        for key in list(self._subscriptions):
            subscribers = self._subscriptions[key]
            subscribers.pop(session, None)
            if not subscribers:
                del self._subscriptions[key]
        self._hooked.discard(id(session))
        self._timeouts.pop(id(session), None)

    def record_timeout(self, session: Any) -> bool:
        """Räkna en tidsgräns i rad; glöm sessionen vid MAX_CONSECUTIVE_TIMEOUTS.

        True om sessionen glömdes.
        """
        count = self._timeouts.get(id(session), 0) + 1
        if count >= MAX_CONSECUTIVE_TIMEOUTS:
            self.forget(session)
            return True
        self._timeouts[id(session)] = count
        return False

    def record_success(self, session: Any) -> None:
        """En notis gick fram: nollställ räkningen av tidsgränser i rad."""
        self._timeouts.pop(id(session), None)

    def subscribers(self, uri: str) -> list[tuple[Any, str]]:
        """(session, prenumererad URI) för alla som prenumererar på uri."""
        try:
            key = canonical_uri(uri)
        except ValueError:
            key = uri
        return list(self._subscriptions.get(key, {}).items())

    def sessions(self) -> list[Any]:
        """Alla sessioner med minst en prenumeration."""
        seen: dict[int, Any] = {}
        for subscribers in self._subscriptions.values():
            for session in subscribers:
                seen.setdefault(id(session), session)
        return list(seen.values())

    def clear(self) -> None:
        self._subscriptions.clear()
        self._hooked.clear()
        self._timeouts.clear()

    def _forget_on_exit(self, session: Any) -> None:
        # BaseSession stänger sin exit-stack när sessionen avslutas. Det är
        # privat API i mcp, så saknas den städas sessionen i stället bort när
        # en notis visar att anslutningen är stängd.
        if id(session) in self._hooked:
            return
        exit_stack = getattr(session, "_exit_stack", None)
        if exit_stack is None:
            return
        exit_stack.callback(self.forget, session)
        self._hooked.add(id(session))


registry = SubscriptionRegistry()


async def _send(session: Any, uri: str) -> None:
    try:
        with anyio.fail_after(SEND_TIMEOUT_SECONDS):
            await session.send_resource_updated(AnyUrl(uri))
    except (anyio.BrokenResourceError, anyio.ClosedResourceError, anyio.EndOfStream):
        logger.info("Sessionen är stängd; prenumerationerna tas bort (%s)", uri)
        registry.forget(session)
    except TimeoutError:
        if registry.record_timeout(session):
            logger.warning(
                "Notisen om %s hann inte skickas inom %s s, %s gånger i rad; sessionen "
                "verkar ha slutat läsa och dess prenumerationer tas bort",
                uri, SEND_TIMEOUT_SECONDS, MAX_CONSECUTIVE_TIMEOUTS,
            )
        else:
            logger.warning("Notisen om %s hann inte skickas inom %s s", uri, SEND_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 — en session får inte stoppa de andra
        logger.warning("Notisen om %s kunde inte skickas: %s", uri, exc)
    else:
        registry.record_success(session)


async def notify_resource_updated(uri: str) -> None:
    """Skicka notifications/resources/updated till alla som prenumererar på uri.

    uri kan anges i valfri form (t.ex. resources.mailbox_uri(mapp)); varje
    session får notisen med den URI den prenumererade med. Kastar aldrig för
    fel i en enskild session.
    """
    targets = registry.subscribers(uri)
    if not targets:
        return
    async with anyio.create_task_group() as tg:
        for session, subscribed_uri in targets:
            tg.start_soon(_send, session, subscribed_uri)


# --- Notiser efter serverns egna skrivverktyg ------------------------------

# Bridges specialmappar som verktygen skriver till (som imap_drafts/imap_client)
_DRAFTS = "Drafts"
_SENT = "Sent"
_TRASH = "Trash"


def _changed_uids(arguments: dict, result: Any) -> list[str]:
    """UID:n som faktiskt ändrades: ok-listan för en lista, annars UID:t."""
    if isinstance(arguments.get("uid"), list):
        if isinstance(result, dict):
            return [str(u) for u in result.get("ok") or []]
        return []
    uid = arguments.get("uid")
    return [] if uid is None else [str(uid)]


def _mailbox_and_emails(arguments: dict, result: Any) -> list[str]:
    uids = _changed_uids(arguments, result)
    if not uids:
        return []
    mailbox = arguments.get("mailbox")
    return [mailbox_uri(mailbox), *(email_uri(mailbox, uid) for uid in uids)]


def _labels(arguments: dict, result: Any) -> list[str]:
    changed = _mailbox_and_emails(arguments, result)
    return [*changed, mailbox_uri(arguments.get("label"))] if changed else []


def _move(arguments: dict, result: Any) -> list[str]:
    changed = _mailbox_and_emails(arguments, result)
    return [*changed, mailbox_uri(arguments.get("target_mailbox"))] if changed else []


def _delete(arguments: dict, result: Any) -> list[str]:
    changed = _mailbox_and_emails(arguments, result)
    if changed and not arguments.get("permanent"):
        changed.append(mailbox_uri(_TRASH))
    return changed


def _folder(arguments: dict, result: Any) -> list[str]:
    return [MAILBOXES_URI, mailbox_uri(arguments.get("name"))]


def _rename(arguments: dict, result: Any) -> list[str]:
    return [MAILBOXES_URI, mailbox_uri(arguments.get("old_name")), mailbox_uri(arguments.get("new_name"))]


def _new_draft(arguments: dict, result: Any) -> list[str]:
    return [mailbox_uri(_DRAFTS)]


def _update_draft(arguments: dict, result: Any) -> list[str]:
    # Det gamla utkastet flyttas till Trash och ett nytt sparas i Drafts
    return [mailbox_uri(_DRAFTS), email_uri(_DRAFTS, arguments.get("uid")), mailbox_uri(_TRASH)]


def _send_draft(arguments: dict, result: Any) -> list[str]:
    return [mailbox_uri(_DRAFTS), email_uri(_DRAFTS, arguments.get("uid")), mailbox_uri(_SENT)]


def _sent(arguments: dict, result: Any) -> list[str]:
    return [mailbox_uri(_SENT)]  # Bridge lägger det skickade mejlet i Sent


# Skrivverktyg → vilka resurser ett lyckat anrop ändrar. Ett nytt skrivverktyg
# ska läggas här eller i TOOLS_WITHOUT_MAILBOX_CHANGES (test_efterfix_resurser_verktygsnotiser).
TOOL_CHANGES: dict[str, Callable[[dict, Any], list[str]]] = {
    "mark_email_read": _mailbox_and_emails,
    "mark_email_unread": _mailbox_and_emails,
    "flag_email": _mailbox_and_emails,
    "unflag_email": _mailbox_and_emails,
    "add_label": _labels,
    "remove_label": _labels,
    "move_email": _move,
    "delete_email": _delete,
    "create_folder": _folder,
    "delete_folder": _folder,
    "rename_folder": _rename,
    "create_draft": _new_draft,
    "create_reply_draft": _new_draft,
    "create_forward_draft": _new_draft,
    "update_draft": _update_draft,
    "send_draft": _send_draft,
    "send_email": _sent,
    "reply_to_email": _sent,
    "forward_email": _sent,
}

# Skrivverktyg som inte ändrar något i brevlådan (get_attachment sparar en fil)
TOOLS_WITHOUT_MAILBOX_CHANGES = frozenset({"get_attachment"})


def changed_uris(tool_name: str, arguments: dict, result: Any) -> list[str]:
    """Resurserna som ett lyckat anrop av tool_name ändrade (utan dubbletter).

    arguments är verktygets argument efter validering. Med en lista UID:n
    räknas bara de som lyckades (result["ok"]). Ett ogiltigt namn hoppas
    över i stället för att kasta.
    """
    rule = TOOL_CHANGES.get(tool_name)
    if rule is None or result is False:
        return []
    try:
        uris = rule(arguments, result)
    except Exception:  # noqa: BLE001 — t.ex. ett mappnamn som saknas
        uris = [MAILBOXES_URI] if rule in (_folder, _rename) else []
    out: list[str] = []
    for uri in uris:
        if uri not in out:
            out.append(uri)
    return out


# Notiser som skickas i bakgrunden (håll referenser så att de inte städas bort)
_pending: set[asyncio.Task] = set()


async def _notify_all(uris: list[str]) -> None:
    try:
        async with anyio.create_task_group() as tg:
            for uri in uris:
                tg.start_soon(notify_resource_updated, uri)
    except Exception as exc:  # noqa: BLE001 — en bakgrundsnotis får aldrig krascha något
        logger.warning("Notiserna om %s kunde inte skickas: %s", ", ".join(uris), exc)


def notify_soon(uris: list[str]) -> None:
    """Skicka notiser om uris i bakgrunden, utan att vänta (fire-and-forget).

    Gör ingenting om ingen prenumererar på någon av dem. Måste anropas i
    serverns event loop (t.ex. från ett verktyg).
    """
    wanted = [uri for uri in uris if registry.subscribers(uri)]
    if not wanted:
        return
    task = asyncio.get_running_loop().create_task(_notify_all(wanted))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def wait_for_pending_notices() -> None:
    """Vänta tills bakgrundsnotiserna skickats (för tester och nedstängning)."""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)


def notify_after_tool(tool_name: str, fn: Callable, args: tuple, kwargs: dict, result: Any) -> None:
    """Efter ett lyckat verktygsanrop: notiser om resurserna det ändrade."""
    bound = inspect.signature(fn).bind_partial(*args, **kwargs)
    bound.apply_defaults()
    notify_soon(changed_uris(tool_name, dict(bound.arguments), result))


def _watched_mailboxes() -> set[str]:
    from .imap_idle import mailbox_key

    try:
        from . import config

        names = config.get_settings().watch_mailbox_list
    except Exception:  # noqa: BLE001 — bara för en loggrad; standardvärdet räcker
        names = ["INBOX"]
    return {mailbox_key(name) for name in names}


def coverage_note(uri: str) -> str | None:
    """Vad en prenumeration på uri ger notis om, när det inte är nya mejl utifrån.

    None för en bevakad mapp (där även nya mejl från omvärlden ger notis).
    Används bara för loggen när en prenumeration godtas.
    """
    from .imap_idle import mailbox_key
    from .resources import parse_mailbox_uri

    if uri.startswith("mailbox://"):
        try:
            name = mailbox_key(parse_mailbox_uri(uri))
        except ValueError:
            return None
        if name in _watched_mailboxes():
            return None
        return (
            f"{uri} ligger utanför PROTONMAIL_WATCH_MAILBOXES: notis bara när serverns egna "
            "verktyg ändrar mappen, inte för nya mejl eller ändringar från andra klienter"
        )
    return (
        f"{uri}: notis bara när serverns egna verktyg ändrar resursen, inte för ändringar "
        "från andra klienter"
    )


def register(server: Any) -> None:
    """Koppla in prenumerationerna på FastMCP-servern. Upprepade anrop gör inget."""
    lowlevel = server._mcp_server
    if getattr(lowlevel, "_protonmail_subscriptions", False):
        return

    @lowlevel.subscribe_resource()
    async def _subscribe(uri: AnyUrl) -> None:
        registry.subscribe(lowlevel.request_context.session, str(uri))
        # Godtas alltid (alla giltiga resurser kan ändras av serverns verktyg, och
        # resources/subscribe har inget svar att lägga en varning i); loggen säger
        # när nya mejl och ändringar utifrån inte ger någon notis.
        note = coverage_note(str(uri))
        if note:
            logger.info("Prenumeration: %s", note)

    @lowlevel.unsubscribe_resource()
    async def _unsubscribe(uri: AnyUrl) -> None:
        registry.unsubscribe(lowlevel.request_context.session, str(uri))

    original = lowlevel.get_capabilities

    def get_capabilities(notification_options, experimental_capabilities):
        capabilities = original(notification_options, experimental_capabilities)
        if capabilities.resources is not None:
            capabilities.resources.subscribe = True
        return capabilities

    lowlevel.get_capabilities = get_capabilities
    lowlevel._protonmail_subscriptions = True

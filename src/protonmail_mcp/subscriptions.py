"""Prenumerationer på resurser (resources/subscribe och notifications/resources/updated).

Klienten prenumererar på en resurs-URI (se resources.py); när resursen ändras
anropar servern notify_resource_updated(uri), och varje session som
prenumererar på den får notisen. URI:er jämförs i kanonisk form
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
import logging
from typing import Any

import anyio
from pydantic import AnyUrl

from .resources import canonical_uri

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


def register(server: Any) -> None:
    """Koppla in prenumerationerna på FastMCP-servern. Upprepade anrop gör inget."""
    lowlevel = server._mcp_server
    if getattr(lowlevel, "_protonmail_subscriptions", False):
        return

    @lowlevel.subscribe_resource()
    async def _subscribe(uri: AnyUrl) -> None:
        registry.subscribe(lowlevel.request_context.session, str(uri))

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

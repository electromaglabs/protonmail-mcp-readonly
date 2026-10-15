import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from ..server import AppContext, mcp
from ._errors import with_error_messages

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger(__name__)


def _get_app(ctx: Context) -> AppContext:
    """Hämta AppContext från MCP Context."""
    return ctx.request_context.lifespan_context


def tool(
    title: str,
    *,
    read_only: bool,
    destructive: bool,
    idempotent: bool,
    open_world: bool,
) -> Callable[[F], F]:
    """Registrera ett verktyg på servern med titel och annoteringar.

    Alla verktyg registreras härigenom. Klassningen måste anges uttryckligen
    (inga standardvärden), så att ett nytt verktyg inte blir felmärkt av
    misstag — MCP:s egna standardvärden är destructiveHint=True och
    openWorldHint=True. tests/unit/test_llm_kontrakt_annoteringar.py har
    tabellen över hur varje verktyg är klassat.

    - read_only: ändrar ingenting (varken brevlåda eller filer)
    - destructive: kan radera, flytta, ersätta eller ta bort något, eller
      gör något som inte kan ångras (skick)
    - idempotent: samma anrop igen ändrar inget mer
    - open_world: når omvärlden (skickar mejl till andra)

    Servern får funktionen omsluten av with_error_messages (tools/_errors.py):
    undantag blir begripliga fel på svenska i stället för interna texter och
    stackspår. Verktyg som inte är read_only omsluts också av notify_after,
    som efter ett lyckat anrop meddelar prenumeranterna på de resurser som
    ändrades (subscriptions.TOOL_CHANGES). Funktionen själv returneras oförändrad, så att den kan
    anropas direkt i tester.
    """
    annotations = ToolAnnotations(
        title=title,
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=open_world,
    )

    def register(fn: F) -> F:
        wrapped = with_error_messages(fn, fn.__name__, open_world=open_world)
        if not read_only:
            wrapped = notify_after(wrapped, fn.__name__)
        mcp.tool(name=fn.__name__, title=title, annotations=annotations)(wrapped)
        return fn

    return register


def notify_after(fn: Callable[..., Any], tool_name: str) -> Callable[..., Any]:
    """Efter-anrop-krok: notiser till prenumeranter när verktyget lyckats.

    Notiserna skickas i bakgrunden (subscriptions.notify_soon), så att
    verktygssvaret aldrig väntar på en långsam session. Ett fel i kroken
    loggas och påverkar aldrig verktygets svar; ett fel i verktyget släpps
    igenom orört och ger ingen notis. Signatur och docstring behålls
    (functools.wraps), så att FastMCP bygger samma schema.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = await fn(*args, **kwargs)
        try:
            from .. import subscriptions

            subscriptions.notify_after_tool(tool_name, fn, args, kwargs, result)
        except Exception as exc:  # noqa: BLE001 — notisen får aldrig fälla verktyget
            logger.warning("Notiser efter %s kunde inte schemaläggas: %s", tool_name, exc)
        return result

    wrapper._notifies_subscribers = True  # type: ignore[attr-defined]
    return wrapper


# Vanliga klassningar
READ_ONLY = dict(read_only=True, destructive=False, idempotent=True, open_world=False)
SETS_STATE = dict(read_only=False, destructive=False, idempotent=True, open_world=False)
ADDS = dict(read_only=False, destructive=False, idempotent=False, open_world=False)
DESTRUCTIVE = dict(read_only=False, destructive=True, idempotent=False, open_world=False)
SENDS = dict(read_only=False, destructive=True, idempotent=False, open_world=True)

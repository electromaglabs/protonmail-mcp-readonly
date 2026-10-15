from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from ..server import AppContext, mcp
from ._errors import with_error_messages

F = TypeVar("F", bound=Callable[..., Any])


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
    stackspår. Funktionen själv returneras oförändrad, så att den kan
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
        mcp.tool(name=fn.__name__, title=title, annotations=annotations)(wrapped)
        return fn

    return register


# Vanliga klassningar
READ_ONLY = dict(read_only=True, destructive=False, idempotent=True, open_world=False)
SETS_STATE = dict(read_only=False, destructive=False, idempotent=True, open_world=False)
ADDS = dict(read_only=False, destructive=False, idempotent=False, open_world=False)
DESTRUCTIVE = dict(read_only=False, destructive=True, idempotent=False, open_world=False)
SENDS = dict(read_only=False, destructive=True, idempotent=False, open_world=True)

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from ..server import AppContext

# Every tool in this fork only reads. Clients that understand tool annotations
# can show that to the user.
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


def _get_app(ctx: Context) -> AppContext:
    """Get the AppContext from the MCP Context."""
    return ctx.request_context.lifespan_context

"""Det enda stället som importerar MCP-SDK:ns serverdelar (mcp 2.x).

Resten av paketet importerar härifrån, så att ett byte av SDK-version bara
ändrar den här filen och de få ställen som använder SDK:ns interna delar
(server.py, resources.py, subscriptions.py).
"""
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.server.mcpserver.resources import DEFAULT_RESOURCE_SECURITY, Resource, ResourceTemplate
from mcp.shared.exceptions import MCPError
from mcp.shared.uri_template import UriTemplate
from mcp.types import INVALID_PARAMS, EmptyResult, SubscribeRequestParams, ToolAnnotations, UnsubscribeRequestParams

__all__ = [
    "DEFAULT_RESOURCE_SECURITY",
    "INVALID_PARAMS",
    "MCPError",
    "Context",
    "EmptyResult",
    "MCPServer",
    "Resource",
    "ResourceError",
    "ResourceTemplate",
    "SubscribeRequestParams",
    "ToolAnnotations",
    "ToolError",
    "UnsubscribeRequestParams",
    "UriTemplate",
]

"""Det enda stället som importerar MCP-SDK:ns serverdelar.

Resten av paketet importerar härifrån, så att ett byte av SDK-version (mcp 1.x
→ 2.x, där FastMCP blev MCPServer) bara ändrar den här filen och de få ställen
som använder SDK:ns interna delar (server.py, resources.py, subscriptions.py).
"""
from mcp.server.fastmcp import Context, FastMCP as MCPServer
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.resources import Resource, ResourceTemplate
from mcp.types import ToolAnnotations

__all__ = ["Context", "MCPServer", "Resource", "ResourceTemplate", "ToolAnnotations", "ToolError"]

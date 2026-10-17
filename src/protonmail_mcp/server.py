"""Read-only MCP server for Proton Mail Bridge.

Six tools, all of which only read: list_mailboxes, get_mailbox_status,
list_emails, get_email, get_email_headers and search_emails. There is no SMTP
code in this fork, so it has no way to send mail.
"""
import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

# Log to stderr only: stdout is reserved for the MCP stdio protocol
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    imap: object  # IMAPClient (typed loosely to avoid importing config early)


def _describe_config_error(exc: Exception) -> str:
    """Summarise a settings error without echoing any setting's value.

    str() of a pydantic ValidationError includes the input values, which for a
    missing username means part of the Bridge password. Only field names and
    messages are used here.
    """
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return type(exc).__name__
    try:
        items = errors(include_url=False, include_context=False, include_input=False)
    except Exception:
        return type(exc).__name__
    parts = []
    for item in items:
        field = ".".join(str(p) for p in item.get("loc", ())) or "settings"
        parts.append(f"{field}: {item.get('msg', 'invalid')}")
    return "; ".join(parts) or type(exc).__name__


@asynccontextmanager
async def lifespan(server: FastMCP):
    from .config import get_settings
    from .imap_client import IMAPClient

    try:
        s = get_settings()
    except Exception as exc:
        summary = _describe_config_error(exc)
        logger.error(
            "Could not read configuration (%s). Check the PROTONMAIL_* settings "
            "(environment variables or .env file); PROTONMAIL_USERNAME and "
            "PROTONMAIL_PASSWORD are required.",
            summary,
        )
        # "from None" keeps the original exception, and the values in it, out
        # of the traceback that ends up in the client's log file.
        raise RuntimeError(f"Invalid configuration: {summary}") from None

    imap = IMAPClient(s)
    try:
        yield AppContext(imap=imap)
    finally:
        await imap.disconnect()


mcp = FastMCP("protonmail-readonly", lifespan=lifespan)


def main() -> None:
    # Import the tools here to avoid a circular import at module level.
    # Only read tools exist in this fork.
    from .tools import mailboxes, messages, search  # noqa: F401

    mcp.run(transport="stdio")


if __name__ == "__main__":
    # Run through the importable module: under "python -m" this file is also
    # loaded as __main__, and the tools register on protonmail_mcp.server.mcp.
    from protonmail_mcp.server import main as _main

    _main()

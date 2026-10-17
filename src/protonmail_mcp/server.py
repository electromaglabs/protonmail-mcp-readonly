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


@asynccontextmanager
async def lifespan(server: FastMCP):
    from .config import get_settings
    from .imap_client import IMAPClient

    try:
        s = get_settings()
    except Exception as exc:
        logger.error(
            "Kunde inte läsa konfiguration: %s\n"
            "Kontrollera att PROTONMAIL_USERNAME och PROTONMAIL_PASSWORD är satta "
            "(miljövariabler eller .env-fil).",
            exc,
        )
        raise

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

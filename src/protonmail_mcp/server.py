import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

# Logging enbart till stderr — stdout är reserverat för MCP stdio-protokollet
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    imap: object  # IMAPClient — undviker tidig import av config
    smtp: object  # SMTPClient


@asynccontextmanager
async def lifespan(server: FastMCP):
    from .config import get_settings
    from .imap_client import IMAPClient
    from .smtp_client import SMTPClient

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

    from .attachments import prepare_attachment_dir

    prepare_attachment_dir(s)  # kastar aldrig, varnar bara
    imap = IMAPClient(s)
    try:
        yield AppContext(imap=imap, smtp=SMTPClient(s))
    finally:
        await imap.disconnect()


mcp = FastMCP("protonmail", lifespan=lifespan)


def register_tools() -> None:
    """Registrera alla verktyg på ``mcp`` (importen av modulerna gör det).

    Importeras här i stället för på modulnivå för att undvika cirkulär import.
    Upprepade anrop gör inget, eftersom modulerna bara importeras en gång.
    """
    from .tools import mailboxes, messages, search, manage, send, reply, folders, drafts, attachments, labels, threads  # noqa: F401


def main() -> None:
    register_tools()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    # python -m protonmail_mcp.server kör filen som modulen __main__, med en
    # egen mcp. Verktygen registreras på protonmail_mcp.server.mcp (det är den
    # verktygsmodulerna importerar), så starta via den riktiga modulen.
    from protonmail_mcp.server import main as _main

    _main()

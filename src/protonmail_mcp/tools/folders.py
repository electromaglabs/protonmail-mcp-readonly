from mcp.server.fastmcp import Context

from ..server import mcp
from . import _get_app


@mcp.tool()
async def create_folder(ctx: Context, name: str) -> bool:
    """Skapa en ny mapp eller etikett i Proton.

    Namnet avgör typen och måste ha ett av prefixen:
    - "Folders/Namn" skapar en mapp. Ett mejl ligger i exakt en mapp.
      Undermappar ("Folders/A/B") går bra om "Folders/A" redan finns.
    - "Labels/Namn" skapar en etikett. Ett mejl kan ha flera etiketter.
      Underetiketter ("Labels/A/B") finns inte i Proton.
    Namn utan prefix avvisas med fel; prefixet sätts inte automatiskt
    eftersom mapp och etikett beter sig olika.

    Args:
        name: Namn med prefix, t.ex. "Folders/Projekt" eller "Labels/Kvitton"

    Returns:
        True när mappen är skapad. Annars kastas ett fel med förklaring.
    """
    app = _get_app(ctx)
    return await app.imap.create_folder(name)


@mcp.tool()
async def delete_folder(ctx: Context, name: str) -> bool:
    """Ta bort en mapp (måste vara tom).

    Args:
        name: Namn på mappen att ta bort
    """
    app = _get_app(ctx)
    return await app.imap.delete_folder(name)


@mcp.tool()
async def rename_folder(ctx: Context, old_name: str, new_name: str) -> bool:
    """Byt namn på en egen mapp (Folders/…) eller etikett (Labels/…).

    Båda namnen måste ha samma prefix: en mapp kan inte bli en etikett eller
    tvärtom. Systemmapparna (INBOX, Sent, Trash, All Mail …) kan inte döpas om.

    Args:
        old_name: Nuvarande namn, t.ex. "Folders/Projekt"
        new_name: Nytt namn med samma prefix, t.ex. "Folders/Projekt 2026"

    Returns:
        True när namnet är bytt. Annars kastas ett fel med förklaring.
    """
    app = _get_app(ctx)
    return await app.imap.rename_folder(old_name, new_name)

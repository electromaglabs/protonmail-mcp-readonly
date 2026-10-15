from mcp.server.fastmcp import Context

from . import _get_app, ADDS, DESTRUCTIVE, tool
from ._types import Mailbox


@tool("Skapa mapp eller etikett", **ADDS)
async def create_folder(ctx: Context, name: Mailbox) -> bool:
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


@tool("Ta bort mapp eller etikett", **DESTRUCTIVE)
async def delete_folder(ctx: Context, name: Mailbox, force: bool = False) -> bool:
    """Ta bort en egen mapp (Folders/…) eller etikett (Labels/…).

    Mappen måste vara tom och sakna undermappar; annars avvisas anropet med
    fel och inget ändras. Med force=True tas den bort ändå. Mejlen raderas inte, men:
    - för en etikett försvinner etiketten från alla mejl som hade den,
    - för en mapp ligger mejlen sedan inte kvar i mappen (de finns i All Mail),
    - vad Proton gör med undermappar och deras mejl är inte känt.
    Systemmapparna (INBOX, Sent, Trash, All Mail …) kan inte tas bort.

    Args:
        name: Namn med prefix, t.ex. "Folders/Gammalt" eller "Labels/Kvitton"
        force: Ta bort även om mappen innehåller mejl (standard: False)

    Returns:
        True när mappen är borttagen. Annars kastas ett fel med förklaring.
    """
    app = _get_app(ctx)
    return await app.imap.delete_folder(name, force=force)


@tool("Byt namn på mapp eller etikett", **DESTRUCTIVE)
async def rename_folder(ctx: Context, old_name: Mailbox, new_name: Mailbox) -> bool:
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

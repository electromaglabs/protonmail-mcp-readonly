from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from .. import imap_labels
from ..imap_bulk import single
from ..server import mcp
from . import _get_app

Mailbox = Annotated[str, Field(min_length=1, max_length=255)]
Label = Annotated[str, Field(min_length=1, max_length=255)]


@mcp.tool()
async def add_label(ctx: Context, uid: str, mailbox: Mailbox, label: Label) -> bool:
    """Lägg till en etikett (Labels/…) på ett mejl. Mejlet ligger kvar i sin mapp.

    I Proton kan ett mejl ha många etiketter men ligger i exakt en mapp.
    Verktyget gör UID COPY till etiketten, vilket hos Bridge betyder "lägg
    till etiketten" — mejlet flyttas inte och inget annat ändras. Har mejlet
    redan etiketten händer inget märkbart.

    Etiketten måste finnas. Skapa den annars först med
    create_folder("Labels/Namn"); list_mailboxes visar vilka som finns.

    Avvisas med fel (inget ändras):
    - etiketten finns inte,
    - label är Starred (använd flag_email), en mapp (Folders/…, använd
      move_email) eller en systemmapp (INBOX, Trash …),
    - mailbox är etiketten själv,
    - UID:t finns inte i mailbox (UID:n gäller per mapp),
    - Bridge nekar (felet innehåller Bridges förklaring).

    Args:
        uid: Mejlets UID i mailbox
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp:
            samma nummer i en annan mapp är ett annat mejl. Använd fältet
            mailbox från svaret av list_emails, search_emails eller get_email.
        label: Etiketten, med eller utan prefix: "Kvitton" eller "Labels/Kvitton"

    Returns:
        True när etiketten är tillagd.
    """
    app = _get_app(ctx)
    return single(await imap_labels.add_label(app.imap, mailbox, [uid], label))


@mcp.tool()
async def remove_label(ctx: Context, uid: str, mailbox: Mailbox, label: Label) -> bool:
    """Ta bort en etikett (Labels/…) från ett mejl utan att röra mejlet i övrigt.

    Mejlet ligger kvar i sin mapp och behåller sina andra etiketter; det
    raderas inte och hamnar inte i Trash. Verktyget letar upp mejlets UID i
    etikettens vy via Message-ID (UID:n gäller per vy) och gör UID EXPUNGE på
    just det UID:t där, vilket hos Bridge bara tar bort etiketten.

    mailbox kan vara mappen där mejlet ligger (t.ex. INBOX) eller etiketten
    själv (t.ex. "Labels/Kvitton" med UID:t från en listning av etiketten).

    Avvisas med fel (inget ändras):
    - mejlet har inte etiketten,
    - etiketten finns inte (create_folder("Labels/Namn") skapar den),
    - label är Starred (använd unflag_email), en mapp eller en systemmapp,
    - UID:t finns inte i mailbox (UID:n gäller per mapp),
    - mejlet saknar Message-ID eller går inte att skilja från ett annat mejl
      i etiketten — ange då etiketten som mailbox och UID:t därifrån,
    - Bridge nekar (felet innehåller Bridges förklaring).

    Args:
        uid: Mejlets UID i mailbox
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp:
            samma nummer i en annan mapp är ett annat mejl. Använd fältet
            mailbox från svaret av list_emails, search_emails eller get_email.
        label: Etiketten, med eller utan prefix: "Kvitton" eller "Labels/Kvitton"

    Returns:
        True när etiketten är borttagen.
    """
    app = _get_app(ctx)
    return single(await imap_labels.remove_label(app.imap, mailbox, [uid], label))

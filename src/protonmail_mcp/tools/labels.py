from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from .. import imap_labels
from ..imap_bulk import BulkResult, single
from . import _get_app, SETS_STATE, tool
from ._types import Mailbox
from ._uids import UidArg

Label = Annotated[str, Field(min_length=1, max_length=255)]


@tool("Lägg till etikett", **SETS_STATE)
async def add_label(ctx: Context, uid: UidArg, mailbox: Mailbox, label: Label) -> bool | BulkResult:
    """Lägg till en etikett (Labels/…) på ett mejl. Mejlet ligger kvar i sin mapp.

    I Proton kan ett mejl ha många etiketter men ligger i exakt en mapp.
    Verktyget gör UID COPY till etiketten, vilket hos Bridge betyder "lägg
    till etiketten" — mejlet flyttas inte och inget annat ändras. Har mejlet
    redan etiketten händer inget märkbart.

    Etiketten måste finnas. Skapa den annars först med
    create_folder("Labels/Namn"); list_mailboxes visar vilka som finns.
    Finns den bara med annan versal/gemen (t.ex. "Faktura" när label är
    "faktura") används den befintliga; skapa ingen dubblett.

    Avvisas med fel (inget ändras):
    - etiketten finns inte, eller finns i flera varianter med olika
      versaler men inte med exakt det namnet (felet räknar upp dem),
    - label är Starred (använd flag_email), en mapp (Folders/…, använd
      move_email) eller en systemmapp (INBOX, Trash …),
    - mailbox är etiketten själv,
    - UID:t finns inte i mailbox (UID:n gäller per mapp),
    - Bridge nekar (felet innehåller Bridges förklaring).

    Args:
        uid: Mejlets UID i mailbox, eller en lista med upp till 100 UID:n ur
            samma mailbox
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp:
            samma nummer i en annan mapp är ett annat mejl. Använd fältet
            mailbox från svaret av list_emails, search_emails eller get_email.
        label: Etiketten, med eller utan prefix: "Kvitton" eller "Labels/Kvitton"

    Returns:
        True när etiketten är tillagd.
        Med en lista med UID:n blir svaret {"ok": [UID, ...], "failed":
        [{"uid": ..., "error": ...}]}: ett resultat per UID. UID:n som inte
        finns i mailbox eller som Bridge nekar hamnar i failed medan de
        andra genomförs. Ett ogiltigt UID (inte heltal) eller fler än 100
        avvisar hela anropet innan något ändras.
    """
    app = _get_app(ctx)
    if isinstance(uid, list):
        return await imap_labels.add_label(app.imap, mailbox, uid, label)
    return single(await imap_labels.add_label(app.imap, mailbox, [uid], label))


@tool("Ta bort etikett", read_only=False, destructive=True, idempotent=True, open_world=False)
async def remove_label(ctx: Context, uid: UidArg, mailbox: Mailbox, label: Label) -> bool | BulkResult:
    """Ta bort en etikett (Labels/…) från ett mejl utan att röra mejlet i övrigt.

    Mejlet ligger kvar i sin mapp och behåller sina andra etiketter; det
    raderas inte och hamnar inte i Trash. Verktyget letar upp mejlets UID i
    etikettens vy via Message-ID (UID:n gäller per vy) och gör UID EXPUNGE på
    just det UID:t där, vilket hos Bridge bara tar bort etiketten.

    mailbox kan vara mappen där mejlet ligger (t.ex. INBOX) eller etiketten
    själv (t.ex. "Labels/Kvitton" med UID:t från en listning av etiketten).

    Avvisas med fel (inget ändras):
    - mejlet har inte etiketten,
    - etiketten finns inte (create_folder("Labels/Namn") skapar den); finns
      den bara med annan versal/gemen används den befintliga, och finns
      flera sådana varianter räknar felet upp dem,
    - label är Starred (använd unflag_email), en mapp eller en systemmapp,
    - UID:t finns inte i mailbox (UID:n gäller per mapp),
    - mejlet saknar ett Message-ID som går att söka på, eller går inte att
      skilja från ett annat mejl i etiketten — ange då etiketten som mailbox
      och UID:t därifrån (i en lista gäller felet bara det UID:t),
    - Bridge nekar (felet innehåller Bridges förklaring).

    Args:
        uid: Mejlets UID i mailbox, eller en lista med upp till 100 UID:n ur
            samma mailbox
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp:
            samma nummer i en annan mapp är ett annat mejl. Använd fältet
            mailbox från svaret av list_emails, search_emails eller get_email.
        label: Etiketten, med eller utan prefix: "Kvitton" eller "Labels/Kvitton"

    Returns:
        True när etiketten är borttagen.
        Med en lista med UID:n blir svaret {"ok": [UID, ...], "failed":
        [{"uid": ..., "error": ...}]}: ett resultat per UID. UID:n som inte
        finns, som saknar etiketten eller som Bridge nekar hamnar i failed
        medan de andra genomförs. Nekar Bridge borttagningen efter att ha
        hunnit med en del, kontrolleras vilka mejl som inte längre har
        etiketten; de räknas som ok. Ett ogiltigt UID (inte heltal) eller fler
        än 100 avvisar hela anropet innan något ändras.
    """
    app = _get_app(ctx)
    if isinstance(uid, list):
        return await imap_labels.remove_label(app.imap, mailbox, uid, label)
    return single(await imap_labels.remove_label(app.imap, mailbox, [uid], label))


@tool("Stjärnmärk mejl", **SETS_STATE)
async def flag_email(ctx: Context, uid: UidArg, mailbox: Mailbox) -> bool | BulkResult:
    """Stjärnmärk ett mejl (Starred i Proton).

    Sätter IMAP-flaggan \\Flagged, som hos Proton är samma sak som Starred:
    mejlet syns sedan under Starred och är stjärnmärkt i alla vyer. Mejlet
    flyttas inte och inget annat ändras. Är det redan stjärnmärkt händer inget.

    Avvisas med fel (inget ändras): UID:t finns inte i mailbox (UID:n gäller
    per mapp), eller Bridge nekar (felet innehåller Bridges förklaring).

    Args:
        uid: Mejlets UID i mailbox, eller en lista med upp till 100 UID:n ur
            samma mailbox
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp:
            samma nummer i en annan mapp är ett annat mejl. Använd fältet
            mailbox från svaret av list_emails, search_emails eller get_email.

    Returns:
        True när mejlet är stjärnmärkt.
        Med en lista med UID:n blir svaret {"ok": [UID, ...], "failed":
        [{"uid": ..., "error": ...}]}: ett resultat per UID. UID:n som inte
        finns i mailbox eller som Bridge nekar hamnar i failed medan de
        andra genomförs. Ett ogiltigt UID (inte heltal) eller fler än 100
        avvisar hela anropet innan något ändras.
    """
    app = _get_app(ctx)
    if isinstance(uid, list):
        return await imap_labels.set_starred(app.imap, mailbox, uid, True)
    return single(await imap_labels.set_starred(app.imap, mailbox, [uid], True))


@tool("Ta bort stjärnmärkning", **SETS_STATE)
async def unflag_email(ctx: Context, uid: UidArg, mailbox: Mailbox) -> bool | BulkResult:
    """Ta bort stjärnmärkningen från ett mejl (Starred i Proton).

    Tar bort IMAP-flaggan \\Flagged, vilket tar bort stjärnan i Proton direkt.
    Bridges Starred-vy uppdateras annars först när Bridge hämtar nästa
    händelse från Proton (var 20:e–40:e sekund), så verktyget tar också bort
    mejlet ur Starred-vyn (bara Starred — mejlet ligger kvar i sin mapp och
    raderas inte). Går det inte är stjärnan ändå borta, men mejlet kan synas
    i Starred, utan \\Flagged, upp till en knapp minut. Är det inte
    stjärnmärkt händer inget.

    Avvisas med fel (inget ändras): UID:t finns inte i mailbox (UID:n gäller
    per mapp), eller Bridge nekar (felet innehåller Bridges förklaring).

    Args:
        uid: Mejlets UID i mailbox (även UID:t från Starred går bra, med
            mailbox="Starred"), eller en lista med upp till 100 UID:n ur samma mailbox
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp:
            samma nummer i en annan mapp är ett annat mejl. Använd fältet
            mailbox från svaret av list_emails, search_emails eller get_email.

    Returns:
        True när stjärnmärkningen är borttagen. Gick det inte att ta bort
        mejlet ur Starred-vyn (stjärnan är ändå borta) blir svaret {"ok":
        [UID], "failed": [], "note": förklaring} i stället.
        Med en lista med UID:n blir svaret {"ok": [UID, ...], "failed":
        [{"uid": ..., "error": ...}]}: ett resultat per UID, med "note" på
        samma sätt. UID:n som inte
        finns i mailbox eller som Bridge nekar hamnar i failed medan de
        andra genomförs. Ett ogiltigt UID (inte heltal) eller fler än 100
        avvisar hela anropet innan något ändras.
    """
    app = _get_app(ctx)
    if isinstance(uid, list):
        return await imap_labels.set_starred(app.imap, mailbox, uid, False)
    res = await imap_labels.set_starred(app.imap, mailbox, [uid], False)
    single(res)
    return res if "note" in res else True

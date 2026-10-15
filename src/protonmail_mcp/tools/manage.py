from mcp.server.fastmcp import Context

from .. import imap_bulk
from ..imap_bulk import BulkResult
from . import _get_app, DESTRUCTIVE, SETS_STATE, tool
from ._types import Mailbox
from ._uids import UidArg


@tool("Markera som läst", **SETS_STATE)
async def mark_email_read(ctx: Context, uid: UidArg, mailbox: Mailbox) -> bool | BulkResult:
    """Markera ett eller flera e-post som lästa.

    Args:
        uid: UID:t som sträng, eller en lista med upp till 100 UID:n ur
            samma mailbox
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp:
            samma nummer i en annan mapp är ett annat mejl. Använd fältet
            mailbox från svaret av list_emails, search_emails eller get_email.

    Returns:
        True när markeringen är gjord. Kastar ett fel om UID:t inte finns i
        mailbox (UID:n gäller per mapp) eller om Bridge nekar.
        Med en lista med UID:n blir svaret {"ok": [UID, ...], "failed":
        [{"uid": ..., "error": ...}]}: ett resultat per UID, i ett enda
        IMAP-kommando. UID:n som inte finns eller som Bridge nekar hamnar i
        failed medan de andra genomförs. Ett ogiltigt UID (inte heltal) eller
        fler än 100 avvisar hela anropet innan något ändras.
    """
    app = _get_app(ctx)
    if isinstance(uid, list):
        return await imap_bulk.set_flags(app.imap, mailbox, uid, r"(\Seen)", add=True)
    return await app.imap.set_flags(mailbox, uid, r"(\Seen)", add=True)


@tool("Markera som oläst", **SETS_STATE)
async def mark_email_unread(ctx: Context, uid: UidArg, mailbox: Mailbox) -> bool | BulkResult:
    """Markera ett eller flera e-post som olästa.

    Args:
        uid: UID:t som sträng, eller en lista med upp till 100 UID:n ur
            samma mailbox
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp:
            samma nummer i en annan mapp är ett annat mejl. Använd fältet
            mailbox från svaret av list_emails, search_emails eller get_email.

    Returns:
        True när markeringen är gjord. Kastar ett fel om UID:t inte finns i
        mailbox (UID:n gäller per mapp) eller om Bridge nekar.
        Med en lista med UID:n blir svaret {"ok": [UID, ...], "failed":
        [{"uid": ..., "error": ...}]}: ett resultat per UID, i ett enda
        IMAP-kommando. UID:n som inte finns eller som Bridge nekar hamnar i
        failed medan de andra genomförs. Ett ogiltigt UID (inte heltal) eller
        fler än 100 avvisar hela anropet innan något ändras.
    """
    app = _get_app(ctx)
    if isinstance(uid, list):
        return await imap_bulk.set_flags(app.imap, mailbox, uid, r"(\Seen)", add=False)
    return await app.imap.set_flags(mailbox, uid, r"(\Seen)", add=False)


@tool("Flytta mejl", **DESTRUCTIVE)
async def move_email(
    ctx: Context, uid: UidArg, target_mailbox: Mailbox, mailbox: Mailbox
) -> bool | BulkResult:
    """Flytta ett e-post till en annan mapp. Bara det angivna mejlet påverkas.

    Verktyget är till för mappar: INBOX, Archive, Spam, Trash och Folders/….
    Mejlet flyttas dit och försvinner ur källmappen.

    Proton skiljer på mappar och etiketter. Är målet en etikett (Labels/…)
    läggs etiketten till och mejlet ligger kvar i källmappen; är källan en
    etikett tas den etiketten bort. För etiketter finns add_label
    och remove_label, för stjärnmärkning flag_email och unflag_email.

    Avvisas med fel (inget ändras):
    - källa och mål är samma mapp (i Trash/Drafts skulle Bridge radera mejlet),
    - flytt till eller från All Mail, och mellan INBOX och Sent (Bridge nekar),
    - flytt till Starred (Bridge skulle ta bort mejlet ur källmappen) —
      stjärnmärk med flag_email i stället,
    - flytt till Trash eller Drafts från en etikett eller Starred, eftersom
      mejlet redan kan ligga där och då raderas permanent,
    - UID:t finns inte i källmappen (UID:n gäller per mapp).
    Vakterna gäller också när en lista med UID:n anges.

    Ligger mejlet redan i Trash (eller Drafts, vid flytt dit) görs ingenting
    med det: ett Proton-mejl kan synas i flera mappar samtidigt, t.ex. ett
    mejl till sig själv i både INBOX och Sent, och Bridges vyer släpar 20–40 s
    efter en flytt. En ny flytt dit skulle få Bridge att radera mejlet
    permanent. Mejlet räknas som ok och svaret förklarar det i "note".

    Args:
        uid: UID:t som sträng, eller en lista med upp till 100 UID:n ur
            samma källmapp
        target_mailbox: Målmapp att flytta till
        mailbox: Källmappen, dvs. mappen som UID:t kom från (obligatorisk).
            UID:n gäller per mapp: samma nummer i en annan mapp är ett annat
            mejl. Använd fältet mailbox från svaret av list_emails,
            search_emails eller get_email.

    Returns:
        True när flytten är klar. Misslyckas den kastas ett fel med Bridges förklaring.
        Låg mejlet redan i Trash/Drafts blir svaret {"ok": [UID], "failed": [],
        "note": "... ligger redan i papperskorgen ..."} i stället för True.
        Med en lista med UID:n blir svaret {"ok": [UID, ...], "failed":
        [{"uid": ..., "error": ...}]}: ett resultat per UID, i ett enda
        IMAP-kommando. UID:n som inte finns eller som Bridge nekar hamnar i
        failed medan de andra genomförs. UID:n vars mejl redan låg i målet
        räknas som ok och nämns i "note". Ett ogiltigt UID (inte heltal) eller
        fler än 100 avvisar hela anropet innan något ändras.
    """
    app = _get_app(ctx)
    if isinstance(uid, list):
        return await imap_bulk.move(app.imap, mailbox, uid, target_mailbox)
    return await app.imap.move_message(mailbox, uid, target_mailbox)


@tool("Radera mejl", **DESTRUCTIVE)
async def delete_email(
    ctx: Context, uid: UidArg, mailbox: Mailbox, permanent: bool = False
) -> bool | BulkResult:
    """Ta bort ett e-post genom att flytta det till papperskorgen (Trash).

    Standard (permanent=False): mejlet flyttas till Trash, precis som "ta bort"
    i Protons egna appar, och kan återställas därifrån. Fungerar från INBOX,
    Archive, Sent, Spam, Drafts och Folders/…. Avvisas med fel om mejlet
    redan ligger i Trash, om mailbox är All Mail (Bridge nekar), och om
    mailbox är en etikett (Labels/…) eller Starred, eftersom mejlet då redan
    kan ligga i Trash och Bridge i så fall raderar det permanent — ange
    mappen där mejlet ligger i stället.

    Ett Proton-mejl kan synas i flera mappar: ett mejl till sig själv är ETT
    mejl i både INBOX och Sent, och Bridges vyer släpar 20–40 s efter en
    flytt. Ligger mejlet redan i Trash (t.ex. Sent-kopian strax efter att
    INBOX-kopian tagits bort) görs ingenting med det, eftersom Bridge då
    skulle radera det permanent; det räknas som ok och svaret förklarar det
    i "note".

    permanent=True: raderar mejlet permanent. Går bara när mailbox är Trash
    (eller Drafts för utkast) och kan inte ångras. Har mejlet kvar en etikett
    tar Bridge bara bort det ur Trash/Drafts. Bara det angivna mejlet påverkas.
    Bridge kan neka raderingen ("Message does not exist", Code=2501) men ändå
    genomföra den när Bridge synkar med Proton; då väntar verktyget upp till
    45 s och räknar mejl som försvunnit som raderade. Ett utkast som då blivit
    kvar i All Mail utan mapp raderas via Trash.

    Args:
        uid: UID:t som sträng, eller en lista med upp till 100 UID:n ur
            samma mailbox
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp:
            samma nummer i en annan mapp är ett annat mejl. Använd fältet
            mailbox från svaret av list_emails, search_emails eller get_email.
        permanent: Radera permanent i stället för att flytta till Trash (standard: False)

    Returns:
        True när mejlet är flyttat eller raderat. Annars kastas ett fel med förklaring,
        t.ex. om UID:t inte finns i mailbox. Låg mejlet redan i Trash blir
        svaret {"ok": [UID], "failed": [], "note": "... ligger redan i
        papperskorgen ..."} i stället för True.
        Med en lista med UID:n blir svaret {"ok": [UID, ...], "failed":
        [{"uid": ..., "error": ...}]}: ett resultat per UID, i ett enda
        IMAP-kommando. UID:n som inte finns eller som Bridge nekar hamnar i
        failed medan de andra genomförs. UID:n vars mejl redan låg i Trash
        räknas som ok och nämns i "note". Ett ogiltigt UID (inte heltal) eller
        fler än 100 avvisar hela anropet innan något ändras.
    """
    app = _get_app(ctx)
    if isinstance(uid, list):
        return await imap_bulk.delete(app.imap, mailbox, uid, permanent=permanent)
    return await app.imap.delete_message(mailbox, uid, permanent=permanent)

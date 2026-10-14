from mcp.server.fastmcp import Context

from ..server import mcp
from . import _get_app


@mcp.tool()
async def mark_email_read(ctx: Context, uid: str, mailbox: str = "INBOX") -> bool:
    """Markera ett e-post som läst.

    Args:
        uid: E-postets UID
        mailbox: Mappnamn (standard: INBOX)
    """
    app = _get_app(ctx)
    return await app.imap.set_flags(mailbox, uid, r"(\Seen)", add=True)


@mcp.tool()
async def mark_email_unread(ctx: Context, uid: str, mailbox: str = "INBOX") -> bool:
    """Markera ett e-post som oläst.

    Args:
        uid: E-postets UID
        mailbox: Mappnamn (standard: INBOX)
    """
    app = _get_app(ctx)
    return await app.imap.set_flags(mailbox, uid, r"(\Seen)", add=False)


@mcp.tool()
async def move_email(
    ctx: Context, uid: str, target_mailbox: str, mailbox: str = "INBOX"
) -> bool:
    """Flytta ett e-post till en annan mapp. Bara det angivna mejlet påverkas.

    Verktyget är till för mappar: INBOX, Archive, Spam, Trash och Folders/….
    Mejlet flyttas dit och försvinner ur källmappen.

    Proton skiljer på mappar och etiketter. Är målet en etikett (Labels/…)
    eller Starred läggs etiketten till och mejlet ligger kvar i källmappen;
    är källan en etikett tas den etiketten bort. Etiketter får egna verktyg.

    Avvisas med fel (inget ändras):
    - källa och mål är samma mapp (i Trash/Drafts skulle Bridge radera mejlet),
    - flytt till eller från All Mail, och mellan INBOX och Sent (Bridge nekar),
    - flytt till Trash eller Drafts från en etikett eller Starred, eftersom
      mejlet redan kan ligga där och då raderas permanent,
    - UID:t finns inte i källmappen (UID:n gäller per mapp).

    Args:
        uid: E-postets UID i källmappen
        target_mailbox: Målmapp att flytta till
        mailbox: Källmapp (standard: INBOX)

    Returns:
        True när flytten är klar. Misslyckas den kastas ett fel med Bridges förklaring.
    """
    app = _get_app(ctx)
    return await app.imap.move_message(mailbox, uid, target_mailbox)


@mcp.tool()
async def delete_email(
    ctx: Context, uid: str, mailbox: str = "INBOX", permanent: bool = False
) -> bool:
    """Ta bort ett e-post genom att flytta det till papperskorgen (Trash).

    Standard (permanent=False): mejlet flyttas till Trash, precis som "ta bort"
    i Protons egna appar, och kan återställas därifrån. Fungerar från INBOX,
    Archive, Sent, Spam, Drafts och Folders/…. Avvisas med fel om mejlet
    redan ligger i Trash, om mailbox är All Mail (Bridge nekar), och om
    mailbox är en etikett (Labels/…) eller Starred, eftersom mejlet då redan
    kan ligga i Trash och Bridge i så fall raderar det permanent — ange
    mappen där mejlet ligger i stället.

    permanent=True: raderar mejlet permanent. Går bara när mailbox är Trash
    (eller Drafts för utkast) och kan inte ångras. Har mejlet kvar en etikett
    tar Bridge bara bort det ur Trash/Drafts. Bara det angivna mejlet påverkas.

    Args:
        uid: E-postets UID i mailbox
        mailbox: Mappnamn (standard: INBOX)
        permanent: Radera permanent i stället för att flytta till Trash (standard: False)

    Returns:
        True när mejlet är flyttat eller raderat. Annars kastas ett fel med förklaring,
        t.ex. om UID:t inte finns i mailbox.
    """
    app = _get_app(ctx)
    return await app.imap.delete_message(mailbox, uid, permanent=permanent)

from mcp.server.fastmcp import Context

from ..attachments import load_for_sending
from . import _get_app, SENDS, tool
from ._types import AttachmentArg, OptionalStr


@tool("Skicka mejl", **SENDS)
async def send_email(
    ctx: Context,
    to: str | list[str],
    subject: str,
    body: str,
    body_html: OptionalStr = None,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    reply_to: OptionalStr = None,
    attachments: AttachmentArg = None,
) -> bool:
    """Skicka ett e-post.

    Args:
        to: Mottagaradress(er) — sträng eller lista
        subject: Ämnesrad
        body: Brödtext i klartext
        body_html: Valfri HTML-version av brödtexten
        cc: Kopia-adress(er)
        bcc: Hemlig kopia-adress(er)
        reply_to: Svarsadress
        attachments: Filer att bifoga — ett filnamn eller en lista, inom bilagekatalogen
            (PROTONMAIL_ATTACHMENT_DIR, standard ~/Downloads/protonmail-mcp).
            Högst 20 filer och 25 MB tillsammans. Filer utanför katalogen
            (även via symlänk) avvisas, och då skickas inget.

    Returns:
        True om e-posten skickades utan fel. Vägrar servern bara några av
        mottagarna kastas ett fel som anger vilka som vägrades och vilka som
        ändå fick mejlet — skicka då inte om till alla.
    """
    files = load_for_sending(attachments)
    app = _get_app(ctx)
    return await app.smtp.send_email(
        to=to,
        subject=subject,
        body=body,
        body_html=body_html,
        cc=cc,
        bcc=bcc,
        reply_to=reply_to,
        **({"attachments": files} if files else {}),
    )

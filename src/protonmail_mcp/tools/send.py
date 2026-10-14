from mcp.server.fastmcp import Context

from ..server import mcp
from . import _get_app
from ._types import OptionalStr


@mcp.tool()
async def send_email(
    ctx: Context,
    to: str | list[str],
    subject: str,
    body: str,
    body_html: OptionalStr = None,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    reply_to: OptionalStr = None,
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

    Returns:
        True om e-posten skickades utan fel. Vägrar servern bara några av
        mottagarna kastas ett fel som anger vilka som vägrades och vilka som
        ändå fick mejlet — skicka då inte om till alla.
    """
    app = _get_app(ctx)
    return await app.smtp.send_email(
        to=to,
        subject=subject,
        body=body,
        body_html=body_html,
        cc=cc,
        bcc=bcc,
        reply_to=reply_to,
    )

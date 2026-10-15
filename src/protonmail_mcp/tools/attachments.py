import base64
import hashlib
from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from .. import attachments as attachment_files
from ..email_parser import _decode_bytes, get_attachment_part
from ..server import mcp
from . import _get_app
from .messages import _not_found


@mcp.tool()
async def get_attachment(
    ctx: Context,
    uid: str,
    mailbox: str,
    index: Annotated[int, Field(ge=0)],
    save: bool = True,
) -> dict:
    """Hämta en bilaga ur ett mejl — spara den i bilagekatalogen eller läs den direkt.

    Mejlet läses med BODY.PEEK, så det markeras inte som läst i Proton.
    Ingenting ändras i brevlådan.

    save=True (standard): bilagan sparas i bilagekatalogen
    (PROTONMAIL_ATTACHMENT_DIR, standard ~/Downloads/protonmail-mcp, skapas
    med rättigheterna 0700 när servern startar). Katalogen används inte om
    den är en symlänk, ligger under en symlänk, ägs av någon annan eller är
    skrivbar för andra. Filnamnet kommer från avsändaren och saneras
    (ingen sökväg, inga kontrolltecken). En befintlig fil skrivs aldrig
    över: vid namnkrock blir det "namn (1).ext". På macOS får filen
    karantänmärkningen com.apple.quarantine, som filer från Mail och Safari,
    så att Gatekeeper varnar innan den körs. Svaret anger sökväg,
    storlek, content_type och sha256 — inte innehållet.

    save=False: innehållet returneras direkt, som text för text/*-bilagor
    (avkodat med bilagans teckenkodning) och annars base64-kodat. Bara upp
    till PROTONMAIL_ATTACHMENT_MAX_INLINE_BYTES (standard 1 MiB); större
    bilagor ger ett fel — använd då save=True.

    Ett bifogat mejl (message/rfc822) hämtas som hela meddelandet (.eml).

    Args:
        uid: Mejlets UID
        mailbox: Mappen som UID:t kom från (obligatorisk). UID:n gäller per mapp.
        index: Bilagans index (0-baserat) i listan attachments från get_email
        save: True = spara i bilagekatalogen (standard), False = returnera innehållet

    Returns:
        mailbox, uid, index, part (MIME-delnummer), filename (som i mejlet),
        content_type, size och sha256, samt antingen path och saved_as
        (save=True) eller encoding ("text"/"base64") och content (save=False).

    Fel (ValueError): okänt UID i mappen, index utanför listan, bilagan är
    större än gränsen för save=False, eller bilagekatalogen går inte att skapa
    eller underkänns (symlänk, fel ägare, skrivbar för andra).
    """
    app = _get_app(ctx)
    raw = await app.imap.get_message(mailbox, uid)
    if raw is None:
        raise _not_found(uid, mailbox)
    found = get_attachment_part(raw, index)
    data = found["data"]
    result = {
        "mailbox": mailbox,
        "uid": uid,
        "index": found["index"],
        "part": found["part"],
        "filename": found["filename"],
        "content_type": found["content_type"],
        "size": found["size"],
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    store = attachment_files.get_store()

    if save:
        path = store.save(found["filename"], data, content_type=found["content_type"])
        return {**result, "path": str(path), "saved_as": path.name}

    if len(data) > store.max_inline_bytes:
        raise ValueError(
            f"Bilagan är {len(data)} byte, över gränsen {store.max_inline_bytes} byte för "
            "save=False — använd save=True för att spara den i bilagekatalogen"
        )
    if found["content_type"].startswith("text/"):
        return {**result, "encoding": "text", "content": _decode_bytes(data, found["charset"])}
    return {**result, "encoding": "base64", "content": base64.b64encode(data).decode("ascii")}

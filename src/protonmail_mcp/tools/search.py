from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from . import _get_app, READ_ONLY, tool
from ._types import OptionalStr
from .messages import _with_mailbox

# Storleksgräns i byte; None = inget villkor
_Size = Annotated[int | None, Field(ge=0, strict=True)]
_Tristate = Annotated[bool | None, Field(strict=True)]


@tool("Sök mejl", **READ_ONLY)
async def search_emails(
    ctx: Context,
    mailbox: str = "INBOX",
    from_addr: OptionalStr = None,
    subject: OptionalStr = None,
    since: OptionalStr = None,
    before: OptionalStr = None,
    unseen: bool | None = None,
    max_results: Annotated[int, Field(ge=1, le=200)] = 50,
    to_addr: OptionalStr = None,
    cc_addr: OptionalStr = None,
    text: OptionalStr = None,
    body: OptionalStr = None,
    flagged: _Tristate = None,
    answered: _Tristate = None,
    larger_than: _Size = None,
    smaller_than: _Size = None,
    has_attachment: _Tristate = None,
) -> dict:
    """Sök e-post med filter. Alla angivna filter måste stämma (AND).

    Sökningen ändrar ingenting: inga flaggor sätts och inget flyttas.

    Ämne, avsändare och mottagare (subject, from_addr, to_addr, cc_addr)
    jämförs mot avkodade headers, så sökningar med å, ä och ö fungerar. Det
    görs lokalt för de 1000 nyaste brev som matchar övriga villkor;
    complete=False och note talar om när inte alla brev kunde kontrolleras.

    text och body söks av Bridge i det okodade meddelandet. Ord med å, ä och ö
    söks därför också i den quoted-printable-form Bridge lagrar texten i
    (och med stor/liten första bokstav). Begränsningar: ett ord som råkar
    radbrytas mitt i av quoted-printable (lång rad) hittas inte — i ett
    stickprov missades ungefär 1 av 20 träffar — och inte heller ord i
    base64-kodade delar eller skrivna som HTML-entiteter (&ouml;).

    has_attachment avgörs ur mejlens MIME-struktur (BODYSTRUCTURE): en del
    märkt som bilaga (Content-Disposition: attachment) räknas. Inbäddade
    bilder, t.ex. en logga i en signatur, räknas inte — get_email kan ändå
    lista sådana bilder med filnamn under attachments. Kontrollen görs lokalt
    för de 1000 nyaste kandidaterna, som för ämne och avsändare.

    Args:
        mailbox: Mappnamn att söka i (standard: INBOX)
        from_addr: Filtrera på avsändare (adress eller namn, delsträng)
        subject: Filtrera på ämnesrad (delsträng, skiftlägesoberoende)
        since: Filtrera e-post efter datum (format: YYYY-MM-DD eller DD-Mon-YYYY)
        before: Filtrera e-post före datum (format: YYYY-MM-DD eller DD-Mon-YYYY)
        unseen: True=bara olästa, False=bara lästa, None=alla
        max_results: Högsta antal träffar, 1–200 (standard: 50). De nyaste returneras.
        to_addr: Filtrera på mottagare i To (adress eller namn, delsträng)
        cc_addr: Filtrera på kopiemottagare i Cc (adress eller namn, delsträng)
        text: Sök i hela meddelandet, headers och brödtext (IMAP TEXT)
        body: Sök bara i brödtexten (IMAP BODY)
        flagged: True=bara stjärnmärkta (Starred), False=bara ej stjärnmärkta, None=alla
        answered: True=bara besvarade, False=bara obesvarade, None=alla
        larger_than: Bara mejl större än så många byte (hela meddelandet med bilagor)
        smaller_than: Bara mejl mindre än så många byte
        has_attachment: True=bara mejl med bilagor, False=bara utan, None=alla

    Returns:
        dict med nycklar: mailbox, messages, total, has_more, complete, note.
        messages är metadata-dicts (uid, mailbox, subject, from, to, cc, date,
        message_id, flags), nyaste först. total är antal hittade träffar (en
        undre gräns när complete är False). UID:t gäller bara i den mapp som
        anges i mailbox.

    Raises:
        ValueError: ogiltigt datum, kontrolltecken (t.ex. radbrytning) i ett
            sökvärde, mappen finns inte, eller Bridge avvisade sökningen.
    """
    app = _get_app(ctx)
    # Nya filter skickas bara när de är satta
    extra = {
        name: value
        for name, value in {
            "to_addr": to_addr,
            "cc_addr": cc_addr,
            "text": text,
            "body": body,
            "flagged": flagged,
            "answered": answered,
            "larger_than": larger_than,
            "smaller_than": smaller_than,
            "has_attachment": has_attachment,
        }.items()
        if value is not None
    }
    result = await app.imap.search_messages(
        mailbox,
        from_addr=from_addr,
        subject=subject,
        since=since,
        before=before,
        unseen=unseen,
        max_results=max_results,
        **extra,
    )
    return {
        **result,
        "mailbox": mailbox,
        "messages": _with_mailbox(result["messages"], mailbox),
    }

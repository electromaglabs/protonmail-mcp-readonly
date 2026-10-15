from typing import Annotated, Any

from pydantic import BeforeValidator, Field

from ..imap_bulk import MAX_UIDS


def _number_to_str(value: Any) -> Any:
    # Klienter skickar ibland UID:n som tal (42 eller [1, 5]); valideringen av
    # själva värdet görs sedan i imap_client/imap_bulk med svenska felmeddelanden
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


Uid = Annotated[str, BeforeValidator(_number_to_str)]

# Ett UID som sträng, eller en lista med 1–100 UID:n ur samma mapp.
# Annotationen är inte `str`, så SDK:n json-tolkar en sträng som ser ut som
# en lista ('["1", "5"]') — det är avsiktligt; "42" förblir strängen "42".
UidArg = Annotated[
    Uid | Annotated[list[Uid], Field(min_length=1, max_length=MAX_UIDS)],
    BeforeValidator(_number_to_str),
    Field(description=(
        "Mejlets UID i mailbox, eller en lista med upp till 100 UID:n ur samma mailbox. "
        'Med en lista blir svaret {"ok": [UID, ...], "failed": [{"uid": ..., "error": ...}]}.'
    )),
]

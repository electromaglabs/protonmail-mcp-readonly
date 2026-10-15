from typing import Annotated, Any

from pydantic import AfterValidator, Field, WithJsonSchema, WrapValidator

from ..attachments import MAX_SEND_FILES

# Valfri strängparameter som inte json-tolkas av FastMCP.
#
# FastMCP:s pre_parse_json kör json.loads på strängvärden för alla parametrar
# vars annotation inte är exakt `str`. Med `str | None` blir strängen "null"
# därför None, och "[1]" en lista. Här är annotationen `str`, så strängen
# lämnas orörd, medan ett uttryckligt JSON-null släpps igenom som None och
# schemat fortfarande visar string|null. Används som `param: OptionalStr = None`.
OptionalStr = Annotated[
    str,
    WrapValidator(lambda value, handler: None if value is None else handler(value)),
    WithJsonSchema({"anyOf": [{"type": "string"}, {"type": "null"}]}),
]

# Mappnamn i alla verktyg (mailbox, target_mailbox och namnen i
# create/delete/rename_folder). Samma gränser som imap_client validerar
# (1–255 tecken), synliga i schemat. Annotationen är `str`, så FastMCP
# json-tolkar inte värdet.
Mailbox = Annotated[str, Field(min_length=1, max_length=255)]


def _one_to_list(value: Any) -> Any:
    return [value] if isinstance(value, str) else value


_FileName = Annotated[str, Field(min_length=1)]

# Filer att bifoga: ett filnamn som sträng, eller en lista med högst
# MAX_SEND_FILES. En ensam sträng blir en lista med ett element, som to/cc/bcc
# tar sträng eller lista.
AttachmentArg = Annotated[
    _FileName | Annotated[list[_FileName], Field(max_length=MAX_SEND_FILES)] | None,
    AfterValidator(_one_to_list),
]

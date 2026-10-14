from typing import Annotated

from pydantic import WithJsonSchema, WrapValidator

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

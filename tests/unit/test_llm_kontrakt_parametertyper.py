"""Enhetstester: samma typ för samma slags parameter i alla verktyg (llm-kontrakt, K7/K8).

Policy för tal och sanningsvärden: LAX (pydantics standardläge) överallt.
"10" tas emot som 10 och "true" som True, men "1.5" som heltal eller "kanske"
som bool avvisas fortfarande, och gränserna (ge/le) gäller. Skälet är att
klienter ibland skickar tal och bool som strängar; att avvisa dem ger
modellen ett engelskt valideringsfel för en ofarlig skillnad i
representation. Samma tanke som att ett UID får vara tal eller sträng.
"""
import inspect
import typing

import pytest
from pydantic.types import Strict

from protonmail_mcp.server import mcp, register_tools
from protonmail_mcp.tools._types import AttachmentArg, Mailbox
from protonmail_mcp.tools._uids import Uid, UidArg
from tests import sdk_support as sdk

register_tools()
TOOLS = {t.name: t for t in sdk.list_tools(mcp)}
MAILBOX_PARAMS = {"mailbox", "target_mailbox", "name", "old_name", "new_name"}


def _params(tool):
    return inspect.signature(inspect.unwrap(tool.fn)).parameters


UID_TOOLS = sorted(name for name, tool in TOOLS.items() if "uid" in _params(tool))


def test_uid_tools_found():
    assert len(UID_TOOLS) == 18


@pytest.mark.parametrize("name", UID_TOOLS)
def test_every_uid_parameter_uses_the_common_uid_type(name):
    assert _params(TOOLS[name])["uid"].annotation in (Uid, UidArg)


@pytest.mark.parametrize("name", ["send_email", "reply_to_email", "forward_email"])
def test_attachments_use_the_common_type(name):
    assert _params(TOOLS[name])["attachments"].annotation is AttachmentArg


def _has_strict(metadata) -> bool:
    return any(isinstance(m, Strict) or getattr(m, "strict", None) for m in metadata)


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_no_parameter_is_strict(name):
    for field_name, field in TOOLS[name].fn_metadata.arg_model.model_fields.items():
        assert not _has_strict(field.metadata), f"{name}.{field_name}"


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_mailbox_parameters_share_one_type(name):
    for param_name, param in _params(TOOLS[name]).items():
        if param_name in MAILBOX_PARAMS and typing.get_origin(param.annotation) is not typing.Literal:
            assert param.annotation is Mailbox, f"{name}.{param_name}"


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_mailbox_schema_shows_the_limits(name):
    props = TOOLS[name].parameters["properties"]
    for param_name in MAILBOX_PARAMS & set(props):
        if "const" in props[param_name] or "enum" in props[param_name]:
            continue
        assert props[param_name].get("minLength") == 1, f"{name}.{param_name}"
        assert props[param_name].get("maxLength") == 255, f"{name}.{param_name}"


async def test_int_uid_becomes_string_in_single_uid_tool():
    from pydantic import TypeAdapter

    assert TypeAdapter(Uid).validate_python(70) == "70"


async def test_bool_is_not_a_uid():
    from pydantic import TypeAdapter, ValidationError

    with pytest.raises(ValidationError):
        TypeAdapter(Uid).validate_python(True)


def test_single_attachment_becomes_list():
    from pydantic import TypeAdapter

    adapter = TypeAdapter(AttachmentArg)
    assert adapter.validate_python("a.pdf") == ["a.pdf"]
    assert adapter.validate_python(["a.pdf", "b.pdf"]) == ["a.pdf", "b.pdf"]
    assert adapter.validate_python(None) is None


def test_attachment_limits_still_apply():
    from pydantic import TypeAdapter, ValidationError

    adapter = TypeAdapter(AttachmentArg)
    with pytest.raises(ValidationError):
        adapter.validate_python("")
    with pytest.raises(ValidationError):
        adapter.validate_python([f"f{i}" for i in range(21)])


def test_attachment_schema_advertises_string_or_list():
    props = TOOLS["send_email"].parameters["properties"]["attachments"]
    types = {t.get("type") for t in props["anyOf"]}
    assert {"string", "array", "null"} <= types

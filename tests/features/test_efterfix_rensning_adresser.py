"""BDD: visad adress = mottagare, och ord med @ i visningsnamn rensas (efterfix-rensning, F6/F7)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.messages import get_email, list_emails

scenarios("efterfix_rensning_adresser.feature")

PLACEHOLDERS = {
    "<taggar>": "".join(chr(0xE0000 + ord(c)) for c in "AB"),
    "<rlo>": "‮",
    "<lro>": "‭",
    "<zw>": "​",
}


def _expand(text: str) -> str:
    for name, value in PLACEHOLDERS.items():
        text = text.replace(name, value)
    return text


def _raw(header: str) -> bytes:
    return (
        f"From: a@x.se\r\n{_expand(header)}\r\nTo: me@me.se\r\nSubject: s\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\nb\r\n"
    ).encode("utf-8")


@given(parsers.parse('ett mejl med rubriken "{header}"'), target_fixture="raw")
def mail_with_header(mock_ctx, header):
    raw = _raw(header)
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@when("jag hämtar mejlet med get_email", target_fixture="result")
def fetch(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX"))


@then(parsers.parse('ska reply_to vara "{addr}"'))
def reply_to_is(result, addr):
    assert result["reply_to"] == [_expand(addr)]


@then(parsers.parse('ska adressen i addresses vara "{addr}"'))
def address_pair_is(result, addr):
    assert result["addresses"]["reply_to"][0][1] == addr


@then("ska inget fält i svaret innehålla osynliga tecken")
def nothing_invisible(result):
    import json
    import unicodedata

    text = json.dumps(result, ensure_ascii=False)
    assert not [c for c in text if unicodedata.category(c) == "Cf" or 0xE0000 <= ord(c) <= 0xE0FFF]


@then("ska suspicious_content nämna osynliga tecken i en adress")
def flags_address(result):
    assert any("i en adress" in r for r in result["suspicious_content"])


@then(parsers.parse('ska headers "{name}" vara "{value}"'))
def header_is(result, name, value):
    assert result["headers"][name] == _expand(value)


@given(parsers.parse('en mejllista där ett mejl har rubriken "{header}"'), target_fixture="raw")
def listing_with_header(mock_ctx, header):
    from protonmail_mcp.imap_client import _parse_fetch_metadata

    hdr = _expand(header).encode("utf-8") + b"\r\nSubject: s\r\n\r\n"
    lines = [
        f"1 FETCH (UID 7 FLAGS () BODY[HEADER.FIELDS (FROM)] {{{len(hdr)}}}".encode(),
        bytearray(hdr),
        b")",
    ]
    messages = _parse_fetch_metadata(lines)
    mock_ctx.request_context.lifespan_context.imap.list_messages.return_value = {
        "messages": messages, "total": 1, "page": 1, "pages": 1, "has_more": False,
    }
    return messages


@when("jag listar mejlen med list_emails", target_fixture="result")
def list_them(mock_ctx, raw):
    return asyncio.run(list_emails(mock_ctx, mailbox="INBOX"))


@then(parsers.parse('ska from i listan vara "{value}"'))
def listed_from(result, value):
    assert result["messages"][0]["from"] == _expand(value)


@then("ska raden i listan ha suspicious_content som nämner osynliga tecken i en adress")
def listed_flag(result):
    assert any("i en adress" in r for r in result["messages"][0]["suspicious_content"])


@then("ska raden i listan sakna suspicious_content")
def listed_no_flag(result):
    assert "suspicious_content" not in result["messages"][0]

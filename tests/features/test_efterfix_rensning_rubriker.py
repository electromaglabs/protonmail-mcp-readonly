"""BDD: get_email_headers rensar och märker rubrikerna (efterfix-rensning, F2)."""
import asyncio
import base64
import json
import unicodedata

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.imap_client import _parse_headers
from protonmail_mcp.tools.messages import get_email_headers

scenarios("efterfix_rensning_rubriker.feature")

TAGS = "".join(chr(0xE0000 + ord(c)) for c in "IGNORE")
PLACEHOLDERS = {
    "<base64 för 'Hej' och taggtecken>": base64.b64encode(("Hej" + TAGS).encode()).decode(),
    "<taggar>": TAGS,
    "<rlo>": "‮",
    "<zw>": "​",
}


def _expand(text: str) -> str:
    for name, value in PLACEHOLDERS.items():
        text = text.replace(name, value)
    return text


@given(parsers.parse('ett mejl vars rubriker är "{header}"'), target_fixture="imap")
def headers_mail(mock_ctx, header):
    # Rubrikerna som IMAP-klientens _parse_headers ger dem (råa värden)
    block = (_expand(header) + "\r\n\r\n").encode("utf-8")
    imap = mock_ctx.request_context.lifespan_context.imap
    imap.get_message_headers.return_value = _parse_headers(block)
    return imap


@when("jag hämtar rubrikerna med get_email_headers", target_fixture="result")
def fetch(mock_ctx, imap):
    return asyncio.run(get_email_headers(mock_ctx, uid="1", mailbox="INBOX"))


@then(parsers.parse('ska rubriken {name} vara "{value}"'))
def header_is(result, name, value):
    assert result[name] == _expand(value)


@then("ska inget fält i svaret innehålla osynliga tecken")
def nothing_invisible(result):
    text = json.dumps(result, ensure_ascii=False)
    assert not [c for c in text if unicodedata.category(c) == "Cf" or 0xE0000 <= ord(c) <= 0xE0FFF]


@then(parsers.parse("ska sanitized räkna {name}"))
def counted(result, name):
    assert result["sanitized"][name] > 0


@then("ska suspicious_content nämna taggtecken")
def flags_tags(result):
    assert any("taggtecken" in r for r in result["suspicious_content"])


@then("ska suspicious_content nämna osynliga tecken i en adress")
def flags_address(result):
    assert any("i en adress" in r for r in result["suspicious_content"])


@then("ska suspicious_content vara tom")
def no_suspicion(result):
    assert result["suspicious_content"] == []


@then("ska svaret ha untrusted_content_notice")
def has_notice(result):
    assert "opålitligt" in result["untrusted_content_notice"]

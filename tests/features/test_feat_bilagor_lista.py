"""BDD-steg för feat_bilagor_lista.feature (index och utplockning av bilagor)."""
import email

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.email_parser import get_attachment_part, parse_email
from tests.feat_bilagor_support import base64_part, multipart, raw_message, text_part

scenarios("feat_bilagor_lista.feature")

FILES = {
    "a.pdf": ("application/pdf", b"%PDF-1.4 a\x00\x01"),
    "b.png": ("image/png", b"\x89PNG\r\n\x1a\n bild"),
}


@pytest.fixture
def state():
    return {}


@given(parsers.parse('ett mejl med brödtext och bilagorna "{first}" och "{second}"'))
def message_with_files(state, first, second):
    parts = [text_part()]
    for name in (first, second):
        ctype, data = FILES[name]
        parts.append(base64_part(ctype, f'; filename="{name}"', data))
    state["raw"] = raw_message(multipart(*parts))


@given(parsers.parse('ett mejl med ett bifogat mejl med ämnet "{subject}"'))
def message_with_eml(state, subject):
    inner = f"From: b@example.se\r\nSubject: {subject}\r\n\r\nInre text\r\n"
    state["raw"] = raw_message(
        multipart(text_part(), "Content-Type: message/rfc822\r\n\r\n" + inner)
    )


@when("mejlet parsas")
def parse(state):
    state["parsed"] = parse_email(state["raw"])


@when(parsers.parse("bilaga {index:d} plockas ut ur det råa mejlet"))
def extract(state, index):
    try:
        state["extracted"] = get_attachment_part(state["raw"], index)
    except ValueError as exc:
        state["error"] = exc


@then(parsers.parse("ska bilagorna ha indexen {indexes}"))
def indexes(state, indexes):
    expected = [int(i) for i in indexes.split(",")]
    assert [a["index"] for a in state["parsed"]["attachments"]] == expected


@then(parsers.parse('ska bilagan med index {index:d} ha delnumret "{part}"'))
def part_number(state, index, part):
    assert state["parsed"]["attachments"][index]["part"] == part


@then(parsers.parse('ska den utplockade bilagan heta "{name}" med typen "{ctype}"'))
def extracted_name(state, name, ctype):
    assert state["extracted"]["filename"] == name
    assert state["extracted"]["content_type"] == ctype


@then(parsers.parse('ska den utplockade bilagan ha typen "{ctype}"'))
def extracted_type(state, ctype):
    assert state["extracted"]["content_type"] == ctype


@then("ska innehållet vara bilagans ursprungliga bytes")
def original_bytes(state):
    assert state["extracted"]["data"] == FILES[state["extracted"]["filename"]][1]


@then(parsers.parse('ska innehållet vara ett mejl med ämnet "{subject}"'))
def eml_content(state, subject):
    assert email.message_from_bytes(state["extracted"]["data"])["Subject"] == subject


@then("ska storleken stämma med listan i get_email")
def size_matches(state):
    listed = parse_email(state["raw"])["attachments"][state["extracted"]["index"]]
    assert state["extracted"]["size"] == listed["size"] == len(state["extracted"]["data"])
    assert state["extracted"]["part"] == listed["part"]


@then(parsers.parse('ska utplockningen avvisas med ett fel som nämner "{text}"'))
def rejected(state, text):
    assert "extracted" not in state
    assert text in str(state["error"])

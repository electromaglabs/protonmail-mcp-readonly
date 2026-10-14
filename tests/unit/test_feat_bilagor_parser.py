"""Enhetstester: bilagelistans index/part och get_attachment_part."""
import pytest

from protonmail_mcp.email_parser import get_attachment_part, parse_email
from tests.feat_bilagor_support import base64_part, multipart, raw_message, text_part

PDF = base64_part("application/pdf", '; filename="a.pdf"', b"%PDF a")
PNG_INLINE_NAMED = (
    "Content-Type: image/png; name=\"logo.png\"\r\nContent-Transfer-Encoding: base64\r\n"
    "Content-ID: <logo>\r\n\r\niVBORw0KGgo="
)
ICS = "Content-Type: text/calendar; charset=utf-8\r\n\r\nBEGIN:VCALENDAR\r\nEND:VCALENDAR"
HTML = "Content-Type: text/html; charset=utf-8\r\n\r\n<p>hej</p>"


def _nested_alternative() -> bytes:
    alt = multipart(text_part("text"), HTML, ICS, boundary="ALT").replace(
        "multipart/mixed", "multipart/alternative"
    )
    related = multipart(alt, PNG_INLINE_NAMED, boundary="REL").replace(
        "multipart/mixed", "multipart/related", 1
    )
    return raw_message(multipart(related, PDF, boundary="MIX"))


STRUCTURES = {
    "enkel pdf": raw_message(
        "Content-Type: application/pdf; name=\"scan.pdf\"\r\n"
        "Content-Transfer-Encoding: base64\r\n\r\nJVBERi0xLjQ="
    ),
    "mixed": raw_message(multipart(text_part(), PDF, PDF.replace("a.pdf", "b.pdf"))),
    "nästlad": _nested_alternative(),
    "bifogat mejl": raw_message(
        multipart(text_part(), "Content-Type: message/rfc822\r\n\r\nSubject: inre\r\n\r\nx\r\n", PDF)
    ),
    "utan bilagor": raw_message(text_part()),
}


@pytest.mark.parametrize("name", list(STRUCTURES))
def test_extraction_matches_listing_for_every_index(name):
    raw = STRUCTURES[name]
    listed = parse_email(raw)["attachments"]
    for i, att in enumerate(listed):
        assert att["index"] == i
        got = get_attachment_part(raw, i)
        for key in ("index", "part", "filename", "content_type", "size"):
            assert got[key] == att[key], (name, i, key)
        assert len(got["data"]) == att["size"]


def test_single_part_message_has_part_1():
    att = parse_email(STRUCTURES["enkel pdf"])["attachments"]
    assert att == [
        {"index": 0, "part": "1", "filename": "scan.pdf", "content_type": "application/pdf", "size": 8}
    ]
    assert get_attachment_part(STRUCTURES["enkel pdf"], 0)["data"] == b"%PDF-1.4"


def test_nested_parts_get_imap_section_numbers():
    att = parse_email(STRUCTURES["nästlad"])["attachments"]
    # related(1) → alternative(1.1) → [text 1.1.1, html 1.1.2, ics 1.1.3]; png 1.2; pdf 2
    assert [(a["part"], a["filename"] or a["content_type"]) for a in att] == [
        ("1.1.3", "text/calendar"),
        ("1.2", "logo.png"),
        ("2", "a.pdf"),
    ]


def test_text_attachment_has_charset():
    raw = raw_message(multipart(text_part(), ICS))
    got = get_attachment_part(raw, 0)
    assert got["charset"] == "utf-8"
    assert got["data"].startswith(b"BEGIN:VCALENDAR")


@pytest.mark.parametrize("index", [-1, 1, 10**9])
def test_index_out_of_range(index):
    with pytest.raises(ValueError, match="1 bilaga"):
        get_attachment_part(STRUCTURES["enkel pdf"], index)


def test_no_attachments_message():
    with pytest.raises(ValueError, match="inga bilagor"):
        get_attachment_part(STRUCTURES["utan bilagor"], 0)

"""Enhetstester för fix-svar: hur SMTPClient bygger och skickar meddelanden."""
from __future__ import annotations

import pytest

from protonmail_mcp.smtp_client import _build_message
from tests.fix_svar_support import capture_smtp, header_addresses, make_client


def _flat_headers(raw: bytes) -> str:
    return raw.split(b"\r\n\r\n", 1)[0].decode("ascii")


# -------------------------------------------------------------------
# B1: icke-ASCII-namn och IDN i adressheaders
# -------------------------------------------------------------------


async def test_non_ascii_display_name_in_to_is_encoded_per_word():
    with capture_smtp() as cap:
        await make_client().send_email(
            to=["Åsa Öberg <asa@x.se>", '"Doe, John" <j@x.com>'],
            subject="Hej",
            body="b",
        )
    assert header_addresses(cap.parsed, "To") == [
        ("Åsa Öberg", "asa@x.se"),
        ("Doe, John", "j@x.com"),
    ]
    # Adressdelen ska stå okodad på tråden, bara namnet får vara encoded-word
    headers = _flat_headers(cap.raw)
    assert "<asa@x.se>" in headers


async def test_non_ascii_names_in_cc_and_reply_to():
    with capture_smtp() as cap:
        await make_client().send_email(
            to="bob@example.com",
            cc=["Örjan Ås <orjan@x.se>"],
            reply_to="Märta Ek <marta@x.se>",
            subject="Hej",
            body="b",
        )
    assert header_addresses(cap.parsed, "Cc") == [("Örjan Ås", "orjan@x.se")]
    assert header_addresses(cap.parsed, "Reply-To") == [("Märta Ek", "marta@x.se")]


async def test_idn_domain_is_punycoded_in_header_and_rcpt():
    with capture_smtp() as cap:
        await make_client().send_email(
            to="Åsa <user@exämple.se>", subject="Hej", body="b"
        )
    assert header_addresses(cap.parsed, "To") == [("Åsa", "user@xn--exmple-cua.se")]
    assert cap.recipients == ["user@xn--exmple-cua.se"]


async def test_rcpt_gets_bare_addresses():
    with capture_smtp() as cap:
        await make_client().send_email(
            to="Åsa Öberg <asa@x.se>",
            cc='"Doe, John" <j@x.com>',
            bcc="Hemlig <h@x.se>",
            subject="Hej",
            body="b",
        )
    assert cap.recipients == ["asa@x.se", "j@x.com", "h@x.se"]


def test_build_message_round_trips_utf8_body_and_html():
    msg = _build_message(
        from_addr="me@proton.me",
        to_list=["a@x.se"],
        subject="Möte på fredag",
        body="Hej på dig",
        body_html="<p>Hej på dig</p>",
    )
    assert msg.get_content_type() == "multipart/alternative"
    assert msg.get_body(("plain",)).get_content().strip() == "Hej på dig"
    assert msg.get_body(("html",)).get_content().strip() == "<p>Hej på dig</p>"
    assert str(msg["Subject"]) == "Möte på fredag"


def test_build_message_rejects_crlf_in_additional_header():
    with pytest.raises(ValueError):
        _build_message(
            from_addr="me@proton.me",
            to_list=["a@x.se"],
            subject="s",
            body="b",
            additional_headers={"References": "<a@x>\r\nBcc: evil@e.com"},
        )


# -------------------------------------------------------------------
# B10: ingen tom To-header
# -------------------------------------------------------------------


def test_build_message_without_to_has_no_to_header():
    msg = _build_message(
        from_addr="me@proton.me", to_list=[], subject="s", body="b"
    )
    assert "To" not in msg


async def test_bcc_only_send_has_no_empty_to_on_the_wire():
    with capture_smtp() as cap:
        await make_client().send_email(to=[], bcc="h@x.se", subject="s", body="b")
    assert b"\r\nTo:" not in cap.raw and not cap.raw.startswith(b"To:")
    assert cap.recipients == ["h@x.se"]

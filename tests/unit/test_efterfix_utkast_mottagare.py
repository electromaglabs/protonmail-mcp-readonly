"""Enhetstester: send_draft skickar till exakt de mottagare som get_email visar (S3)."""
import email
import email.policy

import pytest

from protonmail_mcp.email_parser import parse_email
from protonmail_mcp.smtp_client import prepared_recipients
from tests.fix_svar_support import capture_smtp, make_client

BASE = b"From: me@proton.me\r\nSubject: s\r\nMessage-ID: <d1@proton.me>\r\n"


def _raw(headers: bytes) -> bytes:
    return BASE + headers + b"\r\n\r\nhej\r\n"


def _msg(raw: bytes):
    return email.message_from_bytes(raw, policy=email.policy.SMTP)


class TestDuplicateHeaders:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("extra", [b"To: tvaa@evil.example", b"CC: dold@evil.example",
                                       b"bcc: angripare@evil.example"])
    async def test_second_address_header_refuses_and_sends_nothing(self, extra):
        raw = _raw(b"To: chef@firma.se\r\nCc: c@firma.se\r\nBcc: arkiv@firma.se\r\n" + extra)
        with capture_smtp() as cap:
            with pytest.raises(ValueError, match="rubriker"):
                await make_client().send_prepared_message(_msg(raw))
        assert cap.sent == []


# Fall där parsningen för visning (get_email) och den strukturella parsern
# kan skilja sig (gransk2-sakerhet s2_addr_diff.py, s3_comment_hidden.py)
CASES = [
    b"Bcc: angripare@evil.example (Lindqvist, Anna)",
    b"Bcc: a@x.se (kommentar, b@evil.example)",
    b'Bcc: "a@x.se" <b@evil.example>',
    b"Bcc: grupp: a@x.se, b@evil.example;",
    b"Bcc: a@x.se,\r\n b@evil.example",
    b"Bcc: =?utf-8?q?Chef?= <a@x.se>, <b@evil.example>",
    b"Bcc: a@x.se <b@evil.example>",
    b"Bcc: a@x.se\r\n\tb@evil.example",
    b"Bcc: <a@x.se> <b@evil.example>",
    b"Bcc: a@x.se; b@evil.example",
    b'Bcc: "\\"a@x.se\\"" <b@evil.example>',
    b"Bcc: a@x.se, (x) <b@evil.example>",
    b"Bcc: @route:b@evil.example",
    b"Bcc: <@route:b@evil.example>",
    b'Bcc: "a" <a@x.se>, "b" b@evil.example',
    b"Bcc: a@x.se b@evil.example",
    b"Bcc: undisclosed-recipients:;",
    b"Bcc: =?utf-8?b?YkBldmlsLmV4YW1wbGU=?=",
    b'Bcc: "Doe, J" <j@example.se>, =?utf-8?q?=C3=85sa?= <asa@example.se>',
]


class TestOneInterpretation:
    @pytest.mark.parametrize("header", CASES)
    def test_sent_recipients_are_exactly_the_shown_ones_or_refused(self, header):
        raw = _raw(b"To: t@x.se\r\n" + header)
        shown = parse_email(raw)["addresses"]
        try:
            sent = prepared_recipients(_msg(raw))
        except ValueError:
            return  # vägrat: ingenting skickas
        for key in ("to", "cc", "bcc"):
            assert sent[key] == [a for _, a in shown[key]], key

    def test_comment_with_comma_is_refused(self):
        raw = _raw(b"To: chef@firma.se\r\nBcc: angripare@evil.example (Lindqvist, Anna)")
        assert parse_email(raw)["bcc"] == []
        with pytest.raises(ValueError, match="kan inte tolkas entydigt"):
            prepared_recipients(_msg(raw))

    def test_ordinary_names_and_quoted_commas_are_sent(self):
        raw = _raw(b'To: =?utf-8?q?=C3=85sa?= <asa@example.se>, b@example.se\r\n'
                   b'Cc: "Doe, J" <j@example.se>\r\nBcc: h@example.se')
        assert prepared_recipients(_msg(raw)) == {
            "to": ["asa@example.se", "b@example.se"],
            "cc": ["j@example.se"],
            "bcc": ["h@example.se"],
        }

    def test_idn_domain_is_reported_as_sent(self):
        raw = _raw("To: a@exämple.se".encode())
        assert prepared_recipients(_msg(raw))["to"] == ["a@xn--exmple-cua.se"]

    def test_no_recipients_is_refused(self):
        with pytest.raises(ValueError, match="saknar mottagare"):
            prepared_recipients(_msg(_raw(b"To: undisclosed-recipients:;")))

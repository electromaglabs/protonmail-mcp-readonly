"""Teckenkodning i rubriker och brödtext (PE1, PE11)."""
import email

import pytest

from protonmail_mcp.email_parser import decode_header_value, get_attachments, parse_email


def _mail(content_type: str, body: bytes) -> bytes:
    return (
        b"From: a@b.se\r\nSubject: s\r\nMIME-Version: 1.0\r\n"
        b"Content-Type: " + content_type.encode() + b"\r\n"
        b"Content-Transfer-Encoding: 8bit\r\n\r\n" + body
    )


class TestEncodedWordCharset:
    """Givet ett kodat ord med en teckenkodning Python inte kan använda
    När rubriken avkodas
    Så blir det läsbar text i stället för ett undantag."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("=?x-unknown?Q?hej?=", "hej"),
            ("=?base64?Q?hej?=", "hej"),
            ("=?idna?Q?hej?=", "hej"),
            ("=?utf-8*sv?Q?=C3=A5r?=", "år"),
            ("=?UTF-8*en-US?B?w6Vy?=", "år"),
        ],
    )
    def test_decode_header_value_never_raises(self, value, expected):
        assert decode_header_value(value) == expected

    def test_unknown_charset_in_x_header_does_not_break_parse(self):
        raw = b"From: a@b.se\r\nSubject: ok\r\nX-Foo: =?x-unknown?Q?hej?=\r\n\r\nbody\r\n"
        result = parse_email(raw)
        assert result["subject"] == "ok"

    def test_unknown_charset_in_attachment_filename(self):
        raw = (
            b"From: a@b.se\r\nMIME-Version: 1.0\r\n"
            b'Content-Type: multipart/mixed; boundary="b"\r\n\r\n'
            b"--b\r\nContent-Type: text/plain\r\n\r\nhej\r\n"
            b"--b\r\nContent-Type: application/pdf\r\n"
            b'Content-Disposition: attachment; filename="=?x-unknown?Q?a.pdf?="\r\n\r\n'
            b"%PDF\r\n--b--\r\n"
        )
        attachments = get_attachments(email.message_from_bytes(raw))
        assert attachments[0]["filename"] == "a.pdf"


class TestBodyCharset:
    """Givet en brödtext märkt med en ovanlig eller felaktig teckenkodning
    När mejlet parsas
    Så kraschar det inte och texten blir rimlig."""

    def test_idna_charset_body_does_not_crash(self):
        result = parse_email(_mail("text/plain; charset=idna", b"hej"))
        assert result["body_plain"] == "hej"

    def test_unicode_escape_charset_is_not_interpreted(self):
        result = parse_email(_mail("text/plain; charset=unicode_escape", b"a\\x41b"))
        assert result["body_plain"] == "a\\x41b"

    def test_punycode_charset_gives_text(self):
        result = parse_email(_mail("text/plain; charset=punycode", b"hej"))
        assert result["body_plain"] == "hej"

    def test_utf16_without_bom_falls_back(self):
        result = parse_email(_mail("text/plain; charset=utf-16", "hej då".encode()))
        assert result["body_plain"] == "hej då"

    def test_us_ascii_label_with_utf8_bytes(self):
        result = parse_email(_mail("text/plain; charset=us-ascii", "smörgås".encode()))
        assert result["body_plain"] == "smörgås"

    def test_gb2312_label_with_gbk_bytes(self):
        result = parse_email(_mail("text/plain; charset=gb2312", "镕".encode("gbk")))
        assert result["body_plain"] == "镕"

    def test_x_mac_roman(self):
        result = parse_email(_mail("text/plain; charset=x-mac-roman", "é".encode("mac_roman")))
        assert result["body_plain"] == "é"

    def test_unknown_charset_falls_back_to_latin1_not_replacement(self):
        result = parse_email(_mail("text/plain; charset=x-nonexistent", "Åsa".encode("latin-1")))
        assert result["body_plain"] == "Åsa"


class TestRfc2047Rules:
    """Avkodaren följer RFC 2047 §6.2 och klarar uppdelade tecken."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("(=?ISO-8859-1?Q?a?=)", "(a)"),
            ("(=?ISO-8859-1?Q?a?= b)", "(a b)"),
            ("(=?ISO-8859-1?Q?a?= =?ISO-8859-1?Q?b?=)", "(ab)"),
            ("(=?ISO-8859-1?Q?a?=\r\n    =?ISO-8859-1?Q?b?=)", "(ab)"),
            ("=?utf-8?b?w6U=?= och =?utf-8?q?=C3=B6?=", "å och ö"),
            # "å" (c3 a5) delat mellan två kodade ord
            ("=?utf-8?q?=C3?= =?utf-8?q?=A5?=", "å"),
            ("Re: =?iso-8859-1?q?m=F6te?=", "Re: möte"),
        ],
    )
    def test_decoding(self, value, expected):
        assert decode_header_value(value) == expected

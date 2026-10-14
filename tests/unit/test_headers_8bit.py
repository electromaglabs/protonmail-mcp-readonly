"""get_email_headers lämnar RFC 2047-ord råa (för analys), men rå UTF-8 i en
header ska bli läsbar text, inte ersättningstecken."""
from protonmail_mcp.imap_client import _parse_headers


def test_raw_utf8_header_is_readable():
    raw = "Subject: Möte där\r\nFrom: Åsa <a@x.se>\r\n\r\n".encode("utf-8")
    headers = _parse_headers(raw)
    assert headers["subject"] == "Möte där"
    assert headers["from"] == "Åsa <a@x.se>"


def test_latin1_header_falls_back_without_replacement_chars():
    raw = "Subject: M\xf6te\r\n\r\n".encode("latin-1")
    assert _parse_headers(raw)["subject"] == "Möte"


def test_rfc2047_words_stay_raw():
    raw = b"Subject: =?utf-8?q?M=C3=B6te?=\r\n\r\n"
    assert _parse_headers(raw)["subject"] == "=?utf-8?q?M=C3=B6te?="

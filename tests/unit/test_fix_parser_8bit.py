"""Råa 8-bitars rubriker (PE3/B6)."""
import json

from protonmail_mcp.email_parser import decode_header_value, parse_email

RAW_UTF8 = (
    "From: Åsa Öberg <asa@x.se>\r\nTo: Örjan <o@x.se>\r\n"
    "Subject: Hälsningar från Göteborg\r\nDate: Mån, 1 Jan 2024\r\n"
    "Message-ID: <å@x>\r\nSender: Göran <g@x.se>\r\n\r\nhej\r\n"
).encode()


class TestRawUtf8Headers:
    """Givet ett mejl med rå UTF-8 i rubrikerna (RFC 6532)
    När det parsas
    Så blir alla fält str med rätt tecken, utan U+FFFD."""

    def test_subject_from_to(self):
        r = parse_email(RAW_UTF8)
        assert r["subject"] == "Hälsningar från Göteborg"
        assert r["from"] == "Åsa Öberg <asa@x.se>"
        assert r["to"] == ["Örjan <o@x.se>"]

    def test_date_and_message_id_are_str(self):
        r = parse_email(RAW_UTF8)
        assert type(r["date"]) is str and r["date"] == "Mån, 1 Jan 2024"
        assert type(r["message_id"]) is str and r["message_id"] == "<å@x>"

    def test_headers_dict_is_decoded_text(self):
        r = parse_email(RAW_UTF8)
        assert r["headers"]["Sender"] == "Göran <g@x.se>"
        assert all(type(v) is str for v in r["headers"].values())
        assert "�" not in json.dumps(r, ensure_ascii=False)

    def test_latin1_header_falls_back(self):
        raw = "Subject: Göteborg\r\nFrom: a@b.se\r\n\r\nx\r\n".encode("latin-1")
        assert parse_email(raw)["subject"] == "Göteborg"

    def test_folded_message_id_and_date(self):
        raw = (
            b"Subject: s\r\nFrom: a@b.se\r\nMessage-ID:\r\n <abc@example.com>\r\n"
            b"Date:\r\n Mon, 1 Jan 2024 10:00:00 +0000\r\n\r\nbody\r\n"
        )
        r = parse_email(raw)
        assert r["message_id"] == "<abc@example.com>"
        assert r["date"] == "Mon, 1 Jan 2024 10:00:00 +0000"


class TestDecodeHeaderValueAcceptsHeaderObjects:
    """imap_client skickar compat32-Header-objekt för 8-bitars värden."""

    def test_header_object_with_raw_utf8(self):
        from email.parser import BytesHeaderParser

        hdrs = BytesHeaderParser().parsebytes("Subject: Hälsningar =?utf-8?q?fr=C3=A5n?= x\r\n\r\n".encode())
        assert decode_header_value(hdrs.get("subject")) == "Hälsningar från x"

    def test_surrogateescaped_str(self):
        value = "H\udcc3\udca4lsningar"
        assert decode_header_value(value) == "Hälsningar"

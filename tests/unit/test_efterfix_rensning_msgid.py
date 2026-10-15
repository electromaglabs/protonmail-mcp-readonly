"""F1: Message-ID, In-Reply-To och References visas bara som ASCII-<msg-id>."""
import base64
import time

import pytest

from protonmail_mcp.email_parser import clean_msg_ids, parse_email
from protonmail_mcp.imap_client import _parse_fetch_metadata

HIDDEN = "".join(chr(0xE0000 + ord(c)) for c in "RUN")
ENCODED = "=?utf-8?b?" + base64.b64encode(HIDDEN.encode()).decode() + "?="


class TestCleanMsgIds:
    def test_vanligt_id(self):
        result = clean_msg_ids("<abc@x.se>")
        assert result.text == "<abc@x.se>"
        assert result.removed == {}

    def test_flera_id_med_vikning_och_komma(self):
        assert clean_msg_ids("<a@x>,\r\n <b@y>  <c@z>").text == "<a@x> <b@y> <c@z>"

    def test_kodat_ord_avkodas_inte_men_raknas(self):
        result = clean_msg_ids(f"<x{ENCODED}@x.com>")
        assert result.text == f"<x{ENCODED}@x.com>"
        assert result.removed == {"tag": 3}

    def test_kodat_ord_utan_vinkelparenteser_ger_tomt(self):
        result = clean_msg_ids(ENCODED)
        assert result.text == ""
        assert result.removed == {"tag": 3}

    def test_ra_utf8_i_id_hoppas_over(self):
        result = clean_msg_ids(f"<a@x> <b{HIDDEN}@y> <cå@z>")
        assert result.text == "<a@x>"
        assert result.removed == {"tag": 3}

    def test_skrap_mellan_id_tas_inte_med(self):
        assert clean_msg_ids("hej <a@x> (kommentar) <b@y>").text == "<a@x> <b@y>"

    def test_id_utan_vinkelparenteser_ger_tomt(self):
        assert clean_msg_ids("abc@x.se").text == ""

    def test_kontrolltecken_i_id_hoppas_over(self):
        assert clean_msg_ids("<a\x01b@x> <c@y>").text == "<c@y>"

    def test_tomt_och_none(self):
        assert clean_msg_ids(None).text == ""
        assert clean_msg_ids("").text == ""

    def test_lang_references_ar_linjar(self):
        value = " ".join(f"<{i}@x>" for i in range(200_000))
        start = time.perf_counter()
        assert clean_msg_ids(value).text == value
        assert time.perf_counter() - start < 2.0


def _raw(header: str) -> bytes:
    return f"From: a@x.se\r\nSubject: s\r\n{header}\r\n\r\nb".encode("utf-8")


class TestParseEmail:
    @pytest.mark.parametrize("name,field", [
        ("Message-ID", "message_id"), ("In-Reply-To", "in_reply_to"), ("References", "references"),
    ])
    def test_kodat_ord_i_identifierare(self, name, field):
        result = parse_email(_raw(f"{name}: <x{ENCODED}@x.com>"))
        assert result[field] == f"<x{ENCODED}@x.com>"
        assert result["headers"][name] == f"<x{ENCODED}@x.com>"
        assert HIDDEN not in str(result)
        assert result["sanitized"][field] == 3
        assert any("taggtecken" in r for r in result["suspicious_content"])

    def test_resent_message_id_i_headers(self):
        result = parse_email(_raw(f"Resent-Message-ID: <r{HIDDEN}@x> <ok@x>"))
        assert result["headers"]["Resent-Message-ID"] == "<ok@x>"
        assert result["sanitized"]["headers"] == 3

    def test_vanligt_mejl_oforandrat(self):
        result = parse_email(_raw("Message-ID: <m@x>\r\nIn-Reply-To: <p@x>\r\nReferences: <r@x> <p@x>"))
        assert (result["message_id"], result["in_reply_to"], result["references"]) == (
            "<m@x>", "<p@x>", "<r@x> <p@x>"
        )
        assert result["sanitized"] == {}
        assert result["suspicious_content"] == []


class TestListningar:
    def _row(self, header: str) -> dict:
        hdr = _raw(header).split(b"\r\n\r\n")[0] + b"\r\n\r\n"
        lines = [f"1 FETCH (UID 7 FLAGS () BODY[HEADER] {{{len(hdr)}}}".encode(), bytearray(hdr), b")"]
        return _parse_fetch_metadata(lines, extra_headers=("in-reply-to", "references"))[0]

    @pytest.mark.parametrize("name,field", [
        ("Message-ID", "message_id"), ("In-Reply-To", "in_reply_to"), ("References", "references"),
    ])
    def test_rad_utan_dolda_tecken(self, name, field):
        row = self._row(f"{name}: <x{ENCODED}@x.com> <b{HIDDEN}@y>")
        assert row[field] == f"<x{ENCODED}@x.com>"
        assert HIDDEN not in str(row)
        assert any("taggtecken" in r for r in row["suspicious_content"])

    def test_tradsokningen_far_samma_id(self):
        from protonmail_mcp.imap_threads import _ids_of

        row = self._row("Message-ID: <m@x>\r\nIn-Reply-To: <p@x>\r\nReferences: <r@x>\r\n <p@x>")
        assert _ids_of(row) == ["<m@x>", "<p@x>", "<r@x>"]

"""F6/F7: adresser ändras aldrig i visningen; ord med @ i visningsnamn rensas som text."""
import time

import pytest

from protonmail_mcp.email_parser import parse_email
from protonmail_mcp.sanitize import sanitize_address, sanitize_address_text
from tests.tidsmatning import assert_linear

TAGS = "\U000E0041\U000E0042"
RLO, LRO, ZW = "‮", "‭", "​"


class TestAdressensDoldaTeckenSynliggors:
    """Beslut (koordinatorn): dolda tecken i adressdelen tas varken bort tyst eller
    släpps igenom osynliga — de visas som [U+XXXX] och flaggas."""

    def test_taggtecken_i_ensam_adress_visas_som_koder(self):
        result = sanitize_address(f"boss{TAGS}@company.com")
        assert result.text == "boss[U+E0041][U+E0042]@company.com"
        assert result.removed == {}
        assert result.kept_in_address == 2

    def test_taggtecken_i_vinkeladress_visas_som_koder(self):
        result = sanitize_address_text(f"Boss <boss@company.com{TAGS}>")
        assert result.text == "Boss <boss@company.com[U+E0041][U+E0042]>"
        assert result.kept_in_address == 2

    @pytest.mark.parametrize("ch,code", [
        ("​", "200B"), ("‮", "202E"), ("‎", "200E"), ("‍", "200D"),
        ("﻿", "FEFF"), ("⁠", "2060"), ("️", "FE0F"), ("", "0001"),
        ("­", "00AD"), ("󠀁", "E0001"), ("󠄀", "E0100"),
    ])
    def test_varje_osynligt_tecken_far_en_kod(self, ch, code):
        result = sanitize_address(f"a{ch}b@x.se")
        assert result.text == f"a[U+{code}]b@x.se"
        assert result.kept_in_address == 1

    def test_synliga_tecken_i_adressen_rors_inte(self):
        for addr in ("åsa@exempel.se", "user@[192.0.2.1]", '"a b"@x.se', "é@x.se"):
            assert sanitize_address(addr).text == addr

    def test_bokstavlig_kod_i_adressen_ar_entydig(self):
        # En adress som redan innehåller texten "[U+E0041]" får inte se likadan
        # ut som en adress med ett taggtecken
        literal = sanitize_address("boss[U+E0041]@x.se").text
        escaped = sanitize_address("boss󠁁@x.se").text
        assert literal != escaped
        assert literal == "boss[U+005B]U+E0041]@x.se"

    def test_escapen_ar_deterministisk_och_bara_ascii(self):
        once = sanitize_address(f"a{TAGS}@x.se").text
        assert sanitize_address(f"a{TAGS}@x.se").text == once
        assert once.isascii()

    def test_escapen_ar_linjar(self):
        import time

        addr = "a" + "󠁁" * 500_000 + "@x.se"
        start = time.perf_counter()
        out = sanitize_address(addr)
        assert time.perf_counter() - start < 3.0
        assert out.kept_in_address == 500_000

    def test_taggtecken_i_namnet_tas_fortfarande_bort(self):
        result = sanitize_address_text(f"Bo{TAGS}ss <boss@company.com>")
        assert result.text == "Boss <boss@company.com>"
        assert result.removed == {"tag": 2}

    @pytest.mark.parametrize("header", [
        f"Reply-To: boss{TAGS}@company.com",
        f"Reply-To: Boss <boss@company.com{TAGS}>",
        f"Reply-To: boss{ZW}@company.com",
        f"Reply-To: b{RLO}oss@company.com",
    ])
    def test_get_email_visar_samma_adress_som_svaret_gar_till(self, header):
        from protonmail_mcp.tools.reply import _parse_original, _reply_recipients

        raw = f"From: a@x.se\r\n{header}\r\nTo: me@me.se\r\nSubject: s\r\n\r\nb".encode()
        shown = parse_email(raw)
        to, _ = _reply_recipients(_parse_original(raw), "me@me.se", False, [])
        shown_addr = shown["addresses"]["reply_to"][0][1]
        # Visningen avslöjar exakt rubrikens tecken: avkoda koderna → mottagaren
        import re
        decoded = re.sub(r"\[U\+([0-9A-F]{4,6})\]", lambda m: chr(int(m.group(1), 16)), shown_addr)
        assert decoded in to[0]
        assert shown_addr.isascii()
        assert any("i en adress" in r for r in shown["suspicious_content"])


class TestOrdMedSnabelAIVisningsnamn:
    def test_bidi_i_namn_med_snabel_a_fore_vinkeladress_rensas(self):
        result = sanitize_address_text(f"Bob{RLO}@{LRO}x <b@x.se>")
        assert result.text == "Bob@x <b@x.se>"
        assert result.removed == {"bidi": 2}

    def test_falsk_adress_i_namnet_rensas(self):
        result = sanitize_address_text(f"secure{RLO}@{LRO}paypal.com <evil@x.com>")
        assert result.text == "secure@paypal.com <evil@x.com>"

    def test_citerat_namn_med_snabel_a_rensas(self):
        result = sanitize_address_text(f'"a{ZW}@b" <c@d.se>')
        assert result.text == '"a@b" <c@d.se>'

    def test_varje_element_bedoms_for_sig(self):
        # Första elementet har en vinkeladress (namnordet rensas), andra är en ren adress
        text = f"x{ZW}@y <a@b.se>, c{ZW}@d.se"
        result = sanitize_address_text(text)
        assert result.text == "x@y <a@b.se>, c[U+200B]@d.se"
        assert result.kept_in_address == 1

    def test_ensamma_adresser_utan_namn_far_koder(self):
        assert sanitize_address_text(f"a{ZW}@x.se, b@y.se").text == "a[U+200B]@x.se, b@y.se"

    def test_citerad_lokaldel_ar_fortfarande_adress(self):
        assert sanitize_address_text(f'"an{ZW}na"@x.se').text == '"an[U+200B]na"@x.se'


    def test_from_reserv_utan_adress_rensar_ord_med_snabel_a(self):
        # From går inte att tolka som adress: avkodad text visas, rensad
        raw = f"From: =?utf-8?q?secure=E2=80=AE?=@paypal.com <\r\nSubject: s\r\n\r\nb".encode()
        result = parse_email(raw)
        assert RLO not in result["from"]

    def test_headers_dicten_rensar_ord_med_snabel_a(self):
        raw = f"From: a@x.se\r\nCc: Bob{RLO}@{LRO}x <b@x.se>\r\n\r\nb".encode()
        assert parse_email(raw)["headers"]["Cc"] == "Bob@x <b@x.se>"


class TestListningar:
    def _meta(self, header: str) -> dict:
        from protonmail_mcp.imap_client import _parse_fetch_metadata

        hdr = header.encode("utf-8") + b"\r\n\r\n"
        lines = [f"1 FETCH (UID 7 FLAGS () BODY[HEADER] {{{len(hdr)}}}".encode(), bytearray(hdr), b")"]
        return _parse_fetch_metadata(lines, extra_headers=("cc",))[0]

    def test_cc_med_bidi_i_namnordet_rensas(self):
        assert self._meta(f"Cc: Bob{RLO}@{LRO}x <b@x.se>")["cc"] == "Bob@x <b@x.se>"

    def test_taggtecken_i_adressen_synliggors_och_flaggas(self):
        meta = self._meta(f"From: boss{TAGS}@company.com")
        assert meta["from"] == "boss[U+E0041][U+E0042]@company.com"
        assert any("i en adress" in r for r in meta["suspicious_content"])

    def test_taggtecken_i_amnet_flaggas(self):
        meta = self._meta(f"Subject: Hej{TAGS}")
        assert meta["subject"] == "Hej"
        assert any("taggtecken" in r for r in meta["suspicious_content"])

    def test_bidi_i_namn_flaggas(self):
        meta = self._meta(f"From: Anna{RLO} <a@x.se>")
        assert any("bidi" in r for r in meta["suspicious_content"])

    def test_vanligt_mejl_saknar_nyckeln(self):
        assert "suspicious_content" not in self._meta("From: Anna <a@x.se>\r\nSubject: Hej")


def test_adressraden_ar_linjar():
    # n mot 4n i stället för en absolut gräns, som föll på långsamma maskiner
    assert_linear(
        sanitize_address_text,
        lambda n: ", ".join(f"N{ZW}{i}@x <a{i}@x.se> b{ZW}@y.se" for i in range(n)),
        10_000,
    )

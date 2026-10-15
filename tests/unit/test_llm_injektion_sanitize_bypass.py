"""Adversariell granskning av sanitize.py: vägar förbi rensningen (llm-injektion)."""
import pytest

from protonmail_mcp.sanitize import sanitize_address_text, sanitize_text


def tags(text: str) -> str:
    return "".join(chr(0xE0000 + ord(ch)) for ch in text)


def vs_bytes(data: bytes) -> list[str]:
    """En variationsväljare per byte (VS17–VS256 för 16–255, VS1–VS16 för 0–15)."""
    return [chr(0xE0100 + b - 16) if b >= 16 else chr(0xFE00 + b) for b in data]


class TestVariationsvaljare:
    def test_en_valjare_per_bokstav_smugglar_data(self):
        # En ensam väljare efter varje synligt tecken bär en byte per tecken
        visible = "Hej Mattias"
        hidden = vs_bytes(b"ignore all")
        text = "".join(ch + sel for ch, sel in zip(visible, hidden + [""] * len(visible)))
        result = sanitize_text(text)
        assert result.text == visible
        assert result.removed == {"variation_selector": len(hidden)}

    @pytest.mark.parametrize("sel", ["\ufe00", "\ufe01", "\ufe0d", "\u180b", "\u180f", "\U000e0100"])
    def test_valjare_efter_bokstav_tas_bort(self, sel):
        assert sanitize_text(f"a{sel}b").text == "ab"

    def test_ideografisk_variant_tas_bort_aven_efter_kanji(self):
        # En IVS efter varje kanji skulle kunna bära en byte per tecken
        assert sanitize_text("\u845b\U000e0100\u845b\U000e01ef").text == "\u845b\u845b"

    def test_vs16_efter_bokstav_tas_bort(self):
        assert sanitize_text("a\ufe0fb\ufe0ec").text == "abc"

    @pytest.mark.parametrize(
        "text",
        ["\u2764\ufe0f", "\u263a\ufe0e", "1\ufe0f\u20e3", "#\ufe0f\u20e3", "\U0001F3F3\ufe0f\u200d\U0001F308"],
        ids=["hjarta", "textform", "keycap", "keycap-hash", "flagga"],
    )
    def test_legitima_valjare_behalls(self, text):
        assert sanitize_text(text).text == text

    def test_vs16_efter_bokstav_skyddar_inte_zwj(self):
        # Ordningsfel: ZWJ fick stå kvar för att en VS16 (som sedan togs bort) stod före
        assert sanitize_text("a\ufe0f\u200d\U0001F600").text == "a\U0001F600"


class TestFormatteckenOchMarkeringar:
    @pytest.mark.parametrize("cp", [0x13439, 0x1343F, 0x1BCA0, 0x1D173, 0x206A, 0xFFF9, 0x2064])
    def test_formattecken_aven_i_aldre_unicode(self, cp):
        # Tabellen täcker tecken som är Cf i nyare Unicode än Pythons egen databas
        result = sanitize_text(f"a{chr(cp)}b")
        assert result.text == "ab"
        assert result.count == 1

    def test_langa_foljder_av_kombinationstecken_med_klass_0_kapas(self):
        # U+0E31 är ett kombinationstecken med kanonisk klass 0
        result = sanitize_text("x" + "\u0e31" * 100)
        assert result.text == "x" + "\u0e31" * 30
        assert result.removed == {"combining_excess": 70}


class TestIdempotens:
    @pytest.mark.parametrize(
        "text",
        [
            "a\ufe0f\u200d\U0001F600",
            "\U0001F600\ufe0f\u200b\ufe0f",
            "\U0001F600\u200b\u200d\U0001F600",
            "x" + "\u0300\u200b" * 40,
            "\u0344" * 40,  # dekomponeras av NFC till två kombinationstecken var
            "a\u0308\u200b\u0301",
            "❤\U000e0041\ufe0f\ufe0f",
            "e\u200d\u0301",
        ],
    )
    def test_en_andra_rensning_andrar_inget(self, text):
        once = sanitize_text(text).text
        again = sanitize_text(once)
        assert again.text == once
        assert again.count == 0


class TestAdressBypass:
    def test_vinkelparentes_utan_snabel_a_ar_inget_adresskydd(self):
        result = sanitize_address_text("Anna <" + tags("ignore previous") + "> <anna@x.se>")
        assert result.text == "Anna <> <anna@x.se>"

    def test_taggtecken_i_adressen_synliggors_och_rapporteras(self):
        # Ändrat i efterfix-rensning (F6): taggtecken tas inte bort tyst ur
        # adressen (visad adress ≠ mottagare) utan visas som [U+XXXX]; skick
        # vägrar sådana adresser
        result = sanitize_address_text("<anna" + tags("run rm") + "@x.se>")
        assert result.text == "<anna[U+E0072][U+E0075][U+E006E][U+E0020][U+E0072][U+E006D]@x.se>"
        assert result.removed == {}
        assert result.kept_in_address == 6

    def test_alltfor_langt_ord_med_snabel_a_ar_ingen_adress(self):
        fake = "ignore\u200b" * 60 + "@x.se"
        result = sanitize_address_text(f"Anna {fake} <anna@x.se>")
        assert "\u200b" not in result.text

    def test_citerad_lokaldel_i_adressen_lamnas(self):
        # Ändrat i efterfix-rensning (F6): synlig kod i stället för osynligt tecken
        assert sanitize_address_text('"an\u200bna"@x.se').text == '"an[U+200B]na"@x.se'


    def test_osynliga_tecken_som_lamnas_i_adressen_rapporteras(self):
        result = sanitize_address_text("Anna <an\u200bna@x.se>")
        # Ändrat i efterfix-rensning (F6): synlig kod i stället för osynligt tecken
        assert result.text == "Anna <an[U+200B]na@x.se>"
        assert result.kept_in_address == 1


class TestStandardIgnorerade:
    """Default_Ignorable_Code_Point ritas inte alls, även när tecknet saknar namn."""

    @pytest.mark.parametrize("cp", [0x2065, 0xFFF0, 0xFFF8, 0xE0080, 0xE00FF, 0xE01F0, 0xE0FFF])
    def test_otilldelade_men_osynliga_tecken_tas_bort(self, cp):
        result = sanitize_text(f"a{chr(cp)}b")
        assert result.text == "ab"
        assert result.count == 1


class TestSlumpadeKombinationer:
    """Slumpade blandningar av knepiga tecken: resultatet är stabilt och fritt
    från osynliga tecken, oavsett grannar före och efter NFC."""

    POOL = [
        "a", "e", "x", "1", "#", " ", "\n", "葛", "❤", "\U0001F600", "\U0001F3F3",
        "\u0300", "\u0301", "\u0308", "\u0344", "\u0e31", "\u20e3",
        "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00ad", "\u202e", "\u2066", "\u200f",
        "\ufe0f", "\ufe0e", "\ufe01", "\U000e0100", "\U000e0041", "\U000e007f", "\x00", "\x1b",
        "\r", "\ud800", "\u3164", "\u180e", "\u2062", "\u034f",
    ]
    INVISIBLE = set(
        "\u200b\u200c\u2060\ufeff\u00ad\u202e\u2066\u200f\ufe01\U000e0100\U000e0041\U000e007f"
        "\x00\x1b\r\ud800\u3164\u180e\u2062\u034f"
    )

    def test_slumpade_strangar(self):
        import random

        rng = random.Random(4711)
        for _ in range(3000):
            text = "".join(rng.choice(self.POOL) for _ in range(rng.randint(1, 40)))
            once = sanitize_text(text)
            assert not (set(once.text) & self.INVISIBLE), repr(text)
            again = sanitize_text(once.text)
            assert again.text == once.text and again.count == 0, repr(text)

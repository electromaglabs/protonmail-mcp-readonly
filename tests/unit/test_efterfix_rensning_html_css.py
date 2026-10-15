"""F8c/F8d: CSS-deklarationer tolkas som i en webbläsare (sista gäller, !important, kommentarer)."""
import pytest

from protonmail_mcp.html_text import _declarations, html_to_text


def _shown(style: str) -> str:
    return html_to_text(f'<p>Hej</p><span style="{style}">TEXT</span>')


class TestDeklarationer:
    def test_sista_deklarationen_galler(self):
        assert _declarations("font-size:14px;font-size:0")["font-size"] == ("0", False)

    def test_important_vinner_over_senare(self):
        assert _declarations("display:none!important;display:block")["display"] == ("none", True)

    def test_important_med_blanksteg(self):
        assert _declarations("display: none ! important")["display"] == ("none", True)

    def test_kommentarer_tas_bort(self):
        assert _declarations("display:/**/none")["display"] == ("none", False)
        assert _declarations("dis/* x */play:none")["display"] == ("none", False)

    def test_oavslutad_kommentar_slukar_resten(self):
        assert "display" not in _declarations("color:red;/*display:none")

    def test_gemener_och_blanksteg(self):
        assert _declarations("  DISPLAY :  None ; COLOR: Red ")["display"] == ("none", False)

    def test_skrap_ignoreras(self):
        assert _declarations(";;:x;foo;display:none;")["display"] == ("none", False)


class TestGomdText:
    @pytest.mark.parametrize("style", [
        "font-size:14px;font-size:0",
        "visibility:visible;visibility:hidden",
        "opacity:1;opacity:0",
        "display:/**/none",
        "display:block;display:none",
        "font-size:0!important;font-size:14px",
    ])
    def test_gommande_deklaration_galler(self, style):
        assert _shown(style) == "Hej"

    @pytest.mark.parametrize("style", [
        "font-size:0;font-size:14px",
        "visibility:hidden;visibility:visible",
        "opacity:0;opacity:1",
        "display:none;display:block",
        "color:red;/*display:none*/",
    ])
    def test_synlig_nar_sista_deklarationen_visar(self, style):
        assert _shown(style) == "Hej\n\nTEXT"


def test_oavslutade_kommentarer_ar_linjara():
    import time

    style = "/*" * 200_000
    start = time.perf_counter()
    _declarations(style)
    assert time.perf_counter() - start < 1.0

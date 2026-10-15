"""F9: enkla regler i <style> (klass/element) med display:none eller visibility:hidden."""
import pytest

from protonmail_mcp.html_text import html_to_text, html_to_text_report
from tests.tidsmatning import assert_linear

S = "SECRET"


class TestRegler:
    @pytest.mark.parametrize("css,element", [
        (".h{display:none}", f"<div class=h>{S}</div>"),
        (".h { display : none !important }", f"<div class='x h y'>{S}</div>"),
        ("span.pre{display:none}", f"<span class=pre>{S}</span>"),
        ("blink{display:none}", f"<blink>{S}</blink>"),
        (".a, .h{visibility:hidden}", f"<p class=h>{S}</p>"),
        ("/* kommentar */ .h{display:none}", f"<div class=h>{S}</div>"),
        ("@charset 'utf-8'; .h{display:none}", f"<div class=h>{S}</div>"),
        (".H{display:none}", f"<div class=h>{S}</div>"),
    ])
    def test_regeln_gommer_elementet(self, css, element):
        report = html_to_text_report(f"<style>{css}</style><p>Hej</p>{element}<p>Slut</p>")
        assert S not in report.text
        assert "Slut" in report.text
        assert report.hidden_elements == 1
        # display:none ur en regel har ett eget skäl; visibility räknas som visibility:hidden
        expected = "visibility:hidden" if "visibility" in css else "<style>-regel"
        assert report.hidden_reasons == {expected: 1}

    @pytest.mark.parametrize("css,element", [
        ("@media (max-width:600px){.h{display:none}}", f"<div class=h>{S}</div>"),
        ("@media screen{.a{color:red}} @supports (x){.h{display:none}}", f"<div class=h>{S}</div>"),
        ("div .h{display:none}", f"<div><span class=h>{S}</span></div>"),  # sammansatt väljare
        (".h:hover{display:none}", f"<div class=h>{S}</div>"),
        ("[owa] .h{display:none}", f"<div class=h>{S}</div>"),
        (".h{display:none}", f"<div class=hx>{S}</div>"),
        (".h{display:block}", f"<div class=h>{S}</div>"),
        (".h{display:none}", f"<div class=h style='display:block'>{S}</div>"),
        (".h{display:none;display:block}", f"<div class=h>{S}</div>"),
    ])
    def test_regeln_gommer_inte(self, css, element):
        assert S in html_to_text(f"<style>{css}</style><p>Hej</p>{element}")

    def test_important_i_regeln_vinner_over_inline(self):
        html = f"<style>.h{{display:none!important}}</style><div class=h style='display:block'>{S}</div>"
        assert S not in html_to_text(html)

    def test_visibility_i_regel_kan_aterstallas_av_barn(self):
        html = f"<style>.h{{visibility:hidden}}</style><div class=h>{S}<b style='visibility:visible'>syns</b></div>"
        assert html_to_text(html) == "syns"

    def test_stilen_syns_inte_i_texten(self):
        assert html_to_text("<style>.h{display:none}</style><p>Hej</p>") == "Hej"

    def test_flera_stilblock(self):
        html = f"<style>.a{{color:red}}</style><style>.h{{display:none}}</style><div class=h>{S}</div>x"
        assert html_to_text(html) == "x"


class TestLinjarTid:
    @pytest.mark.parametrize("make", [
        lambda n: "<style>" + ".c{display:none}" * n + "</style>" + "<div class='c d e'>x</div>" * n,
        lambda n: "<style>" + "@media x{" * n + "</style>x",
        lambda n: "<style>" + "{" * n + "</style>x",
        lambda n: "<style>" + "}" * n + "</style>x",
        lambda n: "<style>.h{display:none}</style>" + "<div class='" + "a " * n + "'>x</div>",
        lambda n: "<style>" + "/*" * n + "</style>x",
    ], ids=["manga-regler", "nastlade-media", "oppna", "stangda", "manga-klasser", "kommentarer"])
    def test_tiden_vaxer_linjart(self, make):
        # n mot 4n, bästa av tre (tidigare n mot 2n med en mätning och gränsen
        # 4×, som är precis vad kvadratisk tid ger och som föll under last)
        assert_linear(html_to_text_report, make, 10_000)

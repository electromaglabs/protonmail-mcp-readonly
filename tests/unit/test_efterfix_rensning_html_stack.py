"""F8a/F8b/F10: öppna element följs i en stack, som i en webbläsare."""
import time

import pytest

from protonmail_mcp.html_text import html_to_text, html_to_text_report


class TestForalderStangerGomtElement:
    @pytest.mark.parametrize("html", [
        '<div><span style="font-size:0">x</div>SYNLIG',
        '<div><p style="display:none">x</div>SYNLIG',
        '<table><tr><td style="display:none">x</table><p>SYNLIG',
        '<div><span style="visibility:hidden">x<b>y</div>SYNLIG',
        '<section><div><span style="opacity:0">x</section>SYNLIG',
    ])
    def test_synlig_text_efter_containern(self, html):
        report = html_to_text_report(html)
        assert "SYNLIG" in report.text
        assert "SYNLIG" not in report.hidden_text

    def test_herrelost_sluttagg_stanger_inget(self):
        assert html_to_text('<div style="display:none">x</span>y</div>z') == "z"

    def test_ostangt_gomt_element_utan_forelder_doljer_resten(self):
        assert html_to_text('a<div style="display:none">b<p>c') == "a"

    def test_li_stanger_bara_inom_listan(self):
        html = '<ul><li style="font-size:0">gömd<ul><li>inre</ul></li><li>synlig</ul>'
        text = html_to_text(html)
        assert "synlig" in text and "inre" not in text and "gömd" not in text

    def test_td_i_nastlad_tabell_stanger_inte_yttre_cell(self):
        html = ('<table><tr><td style="display:none"><table><tr><td>a<td>b</table>'
                'fortfarande gömd</td><td>synlig</td></tr></table>')
        text = html_to_text(html)
        assert "synlig" in text and "fortfarande" not in text


class TestSjalvstangande:
    def test_div_med_snedstreck_ar_oppen(self):
        assert html_to_text('<p>Hej</p><div style="display:none"/>SECRET</div>') == "Hej"

    def test_span_med_snedstreck_ar_oppen(self):
        assert html_to_text('<p>Hej</p><span style="font-size:0"/>SECRET</span>') == "Hej"

    def test_void_med_snedstreck_doljer_inget(self):
        assert html_to_text('<img style="display:none"/>synlig') == "synlig"
        assert html_to_text('a<br/>b') == "a\nb"

    def test_snedstreck_utan_stil_paverkar_inte_texten(self):
        assert html_to_text('<p>a</p><div/>b') == "a\n\nb"


class TestDjupNastling:
    @pytest.mark.parametrize("depth", [40, 41, 1000])
    @pytest.mark.parametrize("style", ["font-size:0", "visibility:hidden"])
    def test_gommande_stil_galler_pa_alla_djup(self, depth, style):
        html = "<p>Hej</p>" + "<span style='color:red'>" * depth + f"<i style='{style}'>SECRET</i>" \
               + "</span>" * depth + "<p>Slut</p>"
        report = html_to_text_report(html)
        assert "SECRET" not in report.text
        assert "Slut" in report.text

    def test_aterstalld_stil_pa_djupet(self):
        html = "<div style='font-size:0'>" + "<span style='color:red'>" * 100 + \
               "<b style='font-size:14px'>syns</b>" + "</span>" * 100 + "</div>"
        assert html_to_text(html) == "syns"


class TestLinjarTid:
    @pytest.mark.parametrize("make", [
        lambda n: "<span style='color:red'>" * n + "x" + "</span>" * n,
        lambda n: "<div>" * n + "</span>" * n,
        lambda n: "<li><ul>" + "<span>" * n + "<li>" * n,
        lambda n: "<td><table>" + "<b>" * n + "<td>" * n,
        lambda n: "<div style='display:none'/>" * n,
        lambda n: "<div><span style='font-size:0'>x</div>" * n,
    ], ids=["nastlade-stilar", "felmatchade", "li-utan-scope", "td-utan-scope", "sjalvstangande",
            "containrar"])
    def test_tiden_vaxer_linjart(self, make):
        def run(n):
            html = make(n)
            start = time.perf_counter()
            html_to_text_report(html)
            return time.perf_counter() - start

        small, big = run(20_000), run(40_000)
        assert big < max(small, 0.02) * 4, (small, big)

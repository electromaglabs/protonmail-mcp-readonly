"""Säkerhetsgranskningen: HTML-tolkningen är fail-closed — ett fel ger aldrig mer text till modellen."""
import random

import pytest

from protonmail_mcp import html_text
from protonmail_mcp.email_parser import parse_email
from protonmail_mcp.html_text import _TextExtractor, html_to_text_report

BIG = "9" * 400


def _feed(html: str) -> str:
    """Kör tolken UTAN skyddsnätet i html_to_text_report: inget undantag får uppstå."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


class TestIngaUndantag:
    @pytest.mark.parametrize("style", [
        f"color:rgb({BIG},0,0)", "color:rgb(nan,0,0)", "color:rgb(inf,0,0)", "color:rgb(-inf,0,0)",
        "color:rgba(0,0,0,nan)", f"color:rgba(0,0,0,{BIG})", "color:rgb(1e5%,0,0)",
        f"background:rgb({BIG},{BIG},{BIG})", "opacity:nan", f"opacity:{BIG}", f"left:-{BIG}px",
        f"font-size:{BIG}px", "font:nan/0 a", "clip-path:inset(nan%)", f"clip-path:inset({BIG}%)",
        "position:absolute;clip:rect(nan,nan,nan,nan)", "text-indent:-infpx",
        "\x00display\x00:none", "dïsplay:none", "\\64 isplay:none", "color:\\fffffff",
        "display:none\\", "color:#" + "f" * 10_000,
    ], ids=lambda v: repr(v)[:40])
    def test_stil(self, style):
        _feed(f'<p>Hej</p><span style="{style}">x</span><td bgcolor="rgb({BIG},0,0)">y</td>')

    @pytest.mark.parametrize("css", [
        "/*", "*/", "@media{", "@media (x){.a{", "}}}}", "{{{{", ".h{display:none", "\\", "\\fffffff",
        "\x00.h{display:none}", ".ä{display:none}", ".h{dïsplay:none}", "@" * 1000, ".h{" + "x" * 100_000,
        f".h{{color:rgb({BIG},0,0)}}", "@import url(x); .h{display:none}", ".h{display:none}}",
    ])
    def test_stilmall(self, css):
        _feed(f"<style>{css}</style><p class=h>Hej</p>")

    def test_slumpad_html_och_css(self):
        rng = random.Random(4711)
        frags = ["<", ">", "/", "<div", "<span", "<td", "<style>", "</style>", "</div>", " style='", "'",
                 " class=h", ".h{", "}", "{", "@media", "/*", "*/", ";", ":", "display", "none",
                 "!important", "font:", "0", BIG, "nan", "inf", "-", "%", "px", "color:", "rgb(", ")", ",",
                 "#", "background:", "url(", " bgcolor=", "clip:rect(", "clip-path:inset(", "position:absolute",
                 "left:", "opacity:", "\\", "\x00", "ä", "‮", "&#0;", "<font color=", "SECRET", " "]
        for _ in range(3000):
            _feed("".join(rng.choice(frags) for _ in range(rng.randint(1, 50))))


class TestFelGerAldrigMerText:
    def test_fel_i_stiltolkningen_gommer_elementet(self, monkeypatch):
        original = html_text._soft_style

        def boom(attrs, style):
            if style:
                raise RuntimeError("trasig stil")
            return original(attrs, style)

        monkeypatch.setattr(html_text, "_soft_style", boom)
        report = html_to_text_report('<p>Hej</p><span style="color:red">SECRET</span><p>Slut</p>')
        assert "SECRET" not in report.text
        assert "Slut" in report.text
        assert report.unsafe

    def test_fel_i_stilmallen_flaggas(self, monkeypatch):
        def boom(self, css):
            raise RuntimeError("trasig css")

        monkeypatch.setattr(html_text._Rules, "add_stylesheet", boom)
        report = html_to_text_report("<style>.h{display:none}</style><p>Hej</p>")
        assert report.unsafe
        assert report.text == "Hej"

    def test_fel_mitt_i_tolkningen_slapper_inte_igenom_resten(self, monkeypatch):
        original = _TextExtractor.handle_starttag

        def boom(self, tag, attrs):
            if tag == "b":
                raise RuntimeError("trasig tagg")
            return original(self, tag, attrs)

        monkeypatch.setattr(_TextExtractor, "handle_starttag", boom)
        report = html_to_text_report(
            '<p>Hej</p><div style="display:none">GÖMD</div><b>x</b><style>.y{}</style>EFTER'
        )
        assert "GÖMD" not in report.text
        assert "EFTER" not in report.text
        assert "Hej" in report.text
        assert report.unsafe

    def test_parse_email_flaggar_otolkbar_html(self, monkeypatch):
        original = html_text._soft_style

        def boom(attrs, style):
            if style:
                raise RuntimeError("trasig stil")
            return original(attrs, style)

        monkeypatch.setattr(html_text, "_soft_style", boom)
        raw = b"From: a@b.se\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Hej</p><i style='x:y'>SECRET</i>\r\n"
        result = parse_email(raw)
        assert "SECRET" not in result["body_plain"]
        assert any("kunde inte tolkas säkert" in r for r in result["suspicious_content"])

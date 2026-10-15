"""F9: fler sätt att gömma text i HTML fångas (inline-stilar och attribut)."""
import pytest

from protonmail_mcp.html_text import html_to_text, html_to_text_report

S = "SECRETPAYLOAD"


def _report(inner: str):
    return html_to_text_report(f"<p>Hej</p>{inner}<p>Slut</p>")


class TestGomt:
    @pytest.mark.parametrize("inner", [
        f"<span style='color:transparent'>{S}</span>",
        f"<span style='color:rgba(0,0,0,0)'>{S}</span>",
        f"<span style='color:rgba(10, 20, 30, 0.0)'>{S}</span>",
        f"<span style='color:#0000'>{S}</span>",
        f"<span style='color:#11223300'>{S}</span>",
        f"<span style='font-size:1px'>{S}</span>",
        f"<span style='font-size:0.5pt'>{S}</span>",
        f"<span style='font-size:0.01em'>{S}</span>",
        f"<span style='font-size:0.05rem'>{S}</span>",
        f"<span style='font-size:5%'>{S}</span>",
        f"<span style='font:0/0 a'>{S}</span>",
        f"<span style='font: bold 0px/0 arial'>{S}</span>",
        f"<span style='opacity:0.01'>{S}</span>",
        f"<span style='opacity:5%'>{S}</span>",
        f"<div style='position:absolute;left:-9999px'>{S}</div>",
        f"<div style='position:fixed;top:-2000px'>{S}</div>",
        f"<div style='position:absolute;left:-100em'>{S}</div>",
        f"<div style='text-indent:-9999px;overflow:hidden'>{S}</div>",
        f"<div style='position:absolute;clip:rect(0,0,0,0);width:1px;height:1px;overflow:hidden'>{S}</div>",
        f"<div style='position:absolute;clip:rect(1px 1px 1px 1px)'>{S}</div>",
        f"<div style='clip-path:inset(50%)'>{S}</div>",
        f"<div style='clip-path:circle(0)'>{S}</div>",
        f"<div style='width:0;overflow:hidden'>{S}</div>",
        f"<div style='max-width:0px;overflow:hidden'>{S}</div>",
        f"<div style='background:#ffffff'><span style='color:#ffffff'>{S}</span></div>",
        f"<div style='background-color:#fff'><font color='#fdfdfd'>{S}</font></div>",
        f"<table bgcolor='white'><tr><td><font color=white>{S}</font></td></tr></table>",
        f"<div style='background:#000'><span style='color:#000'>{S}</span></div>",
        f"<div style='background:rgb(20,20,20)'><span style='color:#111'>{S}</span></div>",
        f"<td bgcolor='#336699'><span style='color:#336699'>{S}</span></td>",
    ])
    def test_gomd_text_nar_inte_texten(self, inner):
        report = _report(inner)
        assert S not in report.text
        assert S in report.hidden_text
        assert report.hidden_elements >= 1


class TestSynligt:
    @pytest.mark.parametrize("inner", [
        f"<span style='font-size:2px'>{S}</span>",
        f"<span style='font-size:0.5em'>{S}</span>",
        f"<span style='font:bold 12px arial'>{S}</span>",
        f"<span style='font:400 14px/1.4 sans-serif'>{S}</span>",
        f"<span style='opacity:0.5'>{S}</span>",
        f"<div style='position:relative;left:-9999px'>{S}</div>",
        f"<div style='position:absolute;left:-10px'>{S}</div>",
        f"<div style='text-indent:-20px'>{S}</div>",
        f"<div style='clip:rect(0,0,0,0)'>{S}</div>",  # clip gäller bara positionerade element
        f"<div style='width:0'>{S}</div>",  # utan overflow:hidden syns texten
        f"<div style='background:#000'><span style='color:#fff'>{S}</span></div>",
        f"<td bgcolor='#0057b8'><font color='white'>{S}</font></td>",
        f"<div style='background:#fff url(bg.png)'><span style='color:#fff'>{S}</span></div>",
        f"<div style='background:#fff'><span style='color:#eee'>{S}</span></div>",
        f"<div style='background:#fff'><span style='color:red'>{S}</span></div>",
        f"<div style='background:#000'><span>{S}</span></div>",  # färg okänd (kan komma från CSS)
        f"<div style='background:#fff'><span style='color:#fff;background:#c00'>{S}</span></div>",
        f"<div style='color:transparent'><span style='color:#333'>{S}</span></div>",
    ])
    def test_synlig_text_visas(self, inner):
        assert S in _report(inner).text


class TestVitText:
    @pytest.mark.parametrize("inner", [
        f"<font color='#ffffff'>{S}</font>",
        f"<span style='color:#fdfdfd'>{S}</span>",
        f"<span style='color:rgb(250,250,250)'>{S}</span>",
    ])
    def test_vit_text_utan_kand_bakgrund_raknas_men_visas(self, inner):
        report = _report(inner)
        assert S in report.text
        assert report.white_text == S


def test_skal_for_nya_tekniker():
    html = ("<span style='color:transparent'>a</span>"
            "<div style='background:#fff'><span style='color:#fff'>b</span></div>"
            "<div style='position:absolute;left:-9999px'>c</div>"
            "<div style='clip-path:inset(100%)'>d</div>")
    reasons = html_to_text_report(html).hidden_reasons
    assert reasons == {"color:transparent": 1, "färg=bakgrund": 1, "utanför skärmen": 1, "clip": 1}


def test_linjar_tid_med_manga_fargade_element():
    import time

    def run(n):
        html = "<div style='background:#fff'>" + "<span style='color:#fefefe;font:0/0 a'>x" * n
        start = time.perf_counter()
        html_to_text(html)
        return time.perf_counter() - start

    small, big = run(20_000), run(40_000)
    assert big < max(small, 0.02) * 4

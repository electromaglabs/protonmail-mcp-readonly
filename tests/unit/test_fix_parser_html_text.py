"""HTML → text (K5)."""
import pytest

from protonmail_mcp.html_text import html_to_text


@pytest.mark.parametrize(
    "html, expected",
    [
        # style/script/head läcker inte
        ("<html><head><title>T</title><style>p{color:red}</style></head>"
         "<body><p>Hej</p><script>alert(1)</script></body></html>", "Hej"),
        # entiteter avkodas, &nbsp; blir blanksteg
        ("<p>&amp; &lt;b&gt;&nbsp;x &#229; &auml;</p>", "& <b> x å ä"),
        # blockelement ger radbrytningar
        ("<p>A</p><p>B</p>", "A\n\nB"),
        ("A<br>B<br/>C", "A\nB\nC"),
        ("<div>A</div><div>B</div>", "A\nB"),
        ("<h1>Rubrik</h1>Text", "Rubrik\n\nText"),
        ("<ul><li>a</li><li>b</li></ul>", "- a\n- b"),
        ("<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>", "a b\nc"),
        # '>' i attributvärde läcker inte
        ('<a title="a>b" href="x">länk</a>', "länk"),
        # MSO-villkorskommentarer
        ("<!--[if mso]><p>Bara Outlook</p><![endif]--><p>Alla</p>", "Alla"),
        # blanktecken i källan kollapsas
        ("<p>  många\n   blanksteg  </p>", "många blanksteg"),
        # pre behåller radbrytningar
        ("<pre>rad 1\n  rad 2</pre>", "rad 1\n  rad 2"),
        # blockquote blir citat som stripped kan ta bort
        ("<p>Svar</p><blockquote><p>Citat</p><blockquote>Djupare</blockquote></blockquote>",
         "Svar\n\n> Citat\n>\n> > Djupare"),
        # head utan </head> tappar inte resten av brevet
        ("<head><style>x{}</style><body><p>Text</p>", "Text"),
        # signaturavgränsare bevaras
        ("Hej<br>-- <br>Namn", "Hej\n-- \nNamn"),
        ("", ""),
        ("bara text", "bara text"),
    ],
)
def test_html_to_text(html, expected):
    assert html_to_text(html) == expected


def test_large_input_is_fast():
    import time

    html = "<div><p>" + "ord " * 50_000 + "</p></div>" * 2_000
    start = time.perf_counter()
    html_to_text(html)
    assert time.perf_counter() - start < 2

"""Fynd från granskningen efter buggfixarna (efterfix-parser)."""
import email.header
import time

import pytest

from protonmail_mcp.email_parser import decode_header_value


def _stdlib(value: str) -> str:
    return str(email.header.make_header(email.header.decode_header(value)))


class TestRfc2047IsLinear:
    """S1. Givet en rubrik med tusentals oavslutade kodade ord
    När den avkodas
    Så tar det linjär tid (gränsen ligger hundratals gånger över den
    fixade kodens tid, så testet är inte flakigt), och texten lämnas orörd."""

    @pytest.mark.parametrize(
        "value",
        [
            "\r\n ".join(["=?a?q?x" * 128] * 200),  # vikta rader, ~175 KB
            "=?a?q?x" * 25_000,  # en enda lång rad, ~175 KB
            "\r\n ".join(["=?utf-8?b?QUJD" * 100] * 200),
            "=?" * 80_000,
        ],
        ids=["vikta-q", "en-rad-q", "vikta-b", "bara-start"],
    )
    def test_unterminated_encoded_words_are_fast(self, value):
        start = time.perf_counter()
        result = decode_header_value(value)
        elapsed = time.perf_counter() - start
        assert elapsed < 1, f"tog {elapsed:.2f} s"
        assert result.replace(" ", "") == "".join(value.split())

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("=?utf-8?q?R=C3=A4ksm=C3=B6rg=C3=A5s?=", "Räksmörgås"),
            ("=?UTF-8?B?w6XDpMO2?=", "åäö"),
            ("=?utf-8?b?w6XDpMO2?=\r\n =?utf-8?b?w6XDpMO2?=", "åäöåäö"),
            ("=?iso-8859-1?q?f=F6r?= =?iso-8859-1?q?_dig?=", "för dig"),
            ("Re: =?utf-8?q?m=C3=B6te?= idag", "Re: möte idag"),
            ("=?utf-8?q?Kommer_du=3F?=", "Kommer du?"),
            # okodat '?' sist i ett Q-ord, som vissa klienter skickar
            ("=?utf-8?q?Kommer_du??=", "Kommer du?"),
            # tecken delat mellan två ord
            ("=?utf-8?b?w6U=?= =?utf-8?b?w6Q=?=", "åä"),
            ("=?utf-8?q?=C3?= =?utf-8?q?=A5?=", "å"),
            # två ord utan blanktecken mellan
            ("=?utf-8?q?a?==?utf-8?q?b?=", "ab"),
            # trasigt ord lämnas som text
            ("=?utf-8?q?ok?= =?a?q?x", "ok =?a?q?x"),
            ("100% =?x", "100% =?x"),
            ("Fråga? Svar?=", "Fråga? Svar?="),
        ],
    )
    def test_encoded_words_decode_as_before(self, value, expected):
        assert decode_header_value(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            "=?utf-8?q?R=C3=A4ksm=C3=B6rg=C3=A5s?=",
            "=?UTF-8?B?w6XDpMO2?= och =?iso-8859-1?q?f=F6r?=",
            "Re: =?utf-8?q?m=C3=B6te?= idag",
            "=?utf-8?q?Kommer_du??=",
            "=?windows-1252?q?=80_?= =?utf-8?b?4oKs?=",
        ],
    )
    def test_matches_stdlib_for_ordinary_headers(self, value):
        assert decode_header_value(value) == _stdlib(value)


class TestQuotedLocalPartKeepsSpaces:
    """F5. Givet en adress vars citerade lokaldel innehåller blanksteg
    När adressrubriken parsas
    Så är adressen oförändrad (ett svar går till rätt adress), medan vikning
    och blanktecken utanför citattecken tas bort och radbrytningar aldrig
    kommer med (ingen mottagarinjektion, se 3beab63/bf3d5c1)."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            ('x <"a b"@x.se>', [("x", '"a b"@x.se')]),
            ('"a b"@x.se', [("", '"a b"@x.se')]),
            ('x <"a\tb"@x.se>', [("x", '"a\tb"@x.se')]),
            ('x <"a\\" b"@x.se>', [("x", '"a\\" b"@x.se')]),
            ('x <"a b"@x.se>, y <c@x.se>', [("x", '"a b"@x.se'), ("y", "c@x.se")]),
            # utanför citattecken: vikning och blanktecken bort, som förut
            ("x <a.\r\n b@x.se>", [("x", "a.b@x.se")]),
            ("x <a . b@x.se>", [("x", "a.b@x.se")]),
        ],
    )
    def test_parse_addresses(self, value, expected):
        from protonmail_mcp.email_parser import parse_addresses

        assert parse_addresses(value) == expected

    def test_formatted_address_parses_back_to_the_same_address(self):
        from email.utils import getaddresses

        from protonmail_mcp.email_parser import extract_addresses

        formatted = extract_addresses('Anna <"anna svensson"@x.se>')
        assert formatted == ['Anna <"anna svensson"@x.se>']
        assert [a for _, a in getaddresses(formatted)] == ['"anna svensson"@x.se']

    @pytest.mark.parametrize(
        "value",
        [
            'x <"a\r\n b"@x.se>',
            'x <"a\rb"@x.se>',
            'x <"a\nb"@x.se>',
            'x <"a b"@x.se>',
            'x <"a\x85b"@x.se>',
            'x <"a\x0bb"@x.se>',
            'x <"a\\\r\n b"@x.se>',
        ],
    )
    def test_line_breaks_never_survive_in_the_address(self, value):
        from protonmail_mcp.email_parser import extract_addresses, parse_addresses

        for _, addr in parse_addresses(value):
            assert addr.splitlines() == [addr]
        for formatted in extract_addresses(value):
            assert formatted.splitlines() == [formatted]


class TestUnclosedHead:
    """K5. Givet HTML där <head> aldrig stängs och <body> saknas
    När den görs om till text
    Så stängs head vid första element eller text som inte hör hemma där,
    som i en webbläsare, och brevets innehåll visas."""

    @pytest.mark.parametrize(
        "markup, expected",
        [
            ("<html><head><meta charset='utf-8'><p>Hej Mattias</p></html>", "Hej Mattias"),
            ("<head><title>x</title>\n<div>Innehåll</div>", "Innehåll"),
            ("<head><title>x</title>Bara text", "Bara text"),
            ("<head><link rel=x><base href=y><table><tr><td>a</td></tr></table>", "a"),
            # sådant som hör till head visas fortfarande inte
            ("<head><title>T</title><style>p{}</style><script>x</script>"
             "<meta name=a><noscript><link rel=b></noscript><p>Text</p>", "Text"),
            ("<head>\n  <title>T</title>\n</head><body>Text</body>", "Text"),
            # ett stängt head påverkas inte
            ("<html><head><title>T</title></head><body><p>A</p></body></html>", "A"),
        ],
    )
    def test_html_to_text(self, markup, expected):
        from protonmail_mcp.html_text import html_to_text

        assert html_to_text(markup) == expected

    def test_still_linear(self):
        from protonmail_mcp.html_text import html_to_text

        markup = "<head><meta a=b>" + "<p>x</p><title>t</title>" * 50_000
        start = time.perf_counter()
        text = html_to_text(markup)
        elapsed = time.perf_counter() - start
        assert elapsed < 5, f"tog {elapsed:.2f} s"
        assert text.count("x") == 50_000

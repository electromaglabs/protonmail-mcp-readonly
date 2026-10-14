"""Brödtext, bilagor och body_format (PE2, PE4, PE5, PE8, PE9, PE10, PE12-PE14)."""
import pytest

from protonmail_mcp.email_parser import parse_email


def _alternative(plain: str, html: str) -> bytes:
    return (
        "From: a@b.se\r\nSubject: s\r\nMIME-Version: 1.0\r\n"
        'Content-Type: multipart/alternative; boundary="b"\r\n\r\n'
        f"--b\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{plain}\r\n"
        f"--b\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{html}\r\n--b--\r\n"
    ).encode()


class TestHtmlIsLimited:
    """PE2: max_length/body_format gäller även body_html."""

    BIG = "<html><body>" + "x" * 10_000 + "</body></html>"

    @pytest.mark.parametrize("fmt", ["text", "stripped"])
    def test_html_truncated_in_text_modes(self, fmt):
        result = parse_email(_alternative("hej", self.BIG), body_format=fmt, max_length=500)
        assert result["body_html"].startswith("<html><body>xxx")
        assert len(result["body_html"]) <= 500 + len("\n[...99999 characters remaining]")
        assert "characters remaining]" in result["body_html"]

    def test_html_untruncated_when_max_length_none(self):
        result = parse_email(_alternative("hej", self.BIG), body_format="text", max_length=None)
        assert result["body_html"] == self.BIG

    def test_full_returns_complete_html(self):
        result = parse_email(_alternative("hej", self.BIG), body_format="full", max_length=5)
        assert result["body_html"] == self.BIG

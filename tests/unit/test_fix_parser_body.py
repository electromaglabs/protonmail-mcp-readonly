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


def _multipart(subtype: str, *parts: str, boundary: str = "b") -> str:
    body = "".join(f"--{boundary}\r\n{p}\r\n" for p in parts)
    return f'Content-Type: multipart/{subtype}; boundary="{boundary}"\r\n\r\n{body}--{boundary}--'


def _msg(structure: str) -> bytes:
    return ("From: a@b.se\r\nSubject: s\r\nMIME-Version: 1.0\r\n" + structure + "\r\n").encode()


PLAIN = "Content-Type: text/plain; charset=utf-8\r\n\r\n{}"
HTML = "Content-Type: text/html; charset=utf-8\r\n\r\n{}"
PDF = (
    "Content-Type: application/pdf{params}\r\n{disp}"
    "Content-Transfer-Encoding: base64\r\n\r\nJVBERi0xLjQK"
)


class TestAttachmentDetection:
    """PE5: bilagor avgörs av disposition och filnamn, skiftlägesokänsligt."""

    def _names(self, raw):
        return [a["filename"] for a in parse_email(raw)["attachments"]]

    def test_zip_without_disposition_is_attachment(self):
        raw = _msg(_multipart(
            "mixed", PLAIN.format("hej"),
            'Content-Type: application/zip; name="x.zip"\r\n\r\nPK',
        ))
        assert self._names(raw) == ["x.zip"]

    def test_uppercase_attachment_disposition(self):
        raw = _msg(_multipart(
            "mixed", PLAIN.format("hej"),
            PDF.format(params="", disp='Content-Disposition: ATTACHMENT; filename="avtal.pdf"\r\n'),
        ))
        assert self._names(raw) == ["avtal.pdf"]

    def test_filename_containing_word_attachment_is_not_special(self):
        raw = _msg(_multipart(
            "mixed", PLAIN.format("hej"),
            'Content-Type: text/plain\r\nContent-Disposition: inline; filename="attachment-notes.txt"'
            "\r\n\r\nanteckning",
        ))
        result = parse_email(raw, body_format="full")
        assert result["attachments"] == []
        assert "anteckning" in result["body_plain"]

    def test_text_part_with_name_and_no_disposition_is_not_body(self):
        raw = _msg(_multipart(
            "mixed", PLAIN.format("Riktig text"),
            'Content-Type: text/plain; name="server.log"\r\n\r\nloggrad',
        ))
        result = parse_email(raw, body_format="full")
        assert result["body_plain"].strip() == "Riktig text"
        assert [a["filename"] for a in result["attachments"]] == ["server.log"]

    def test_related_inline_image_without_filename_is_not_attachment(self):
        raw = _msg(_multipart(
            "alternative",
            PLAIN.format("text"),
            _multipart(
                "related", HTML.format('<img src="cid:logo">'),
                "Content-Type: image/png\r\nContent-ID: <logo>\r\n\r\nPNG",
                boundary="r",
            ),
        ))
        result = parse_email(raw, body_format="full")
        assert result["attachments"] == []
        assert result["body_plain"].strip() == "text"
        assert 'cid:logo' in result["body_html"]


class TestBodyStructure:
    """PE4, PE8, PE9: brödtexten hör till ytterbrevet och tas med i sin helhet."""

    def test_alternative_in_mixed_picks_one_of_each(self):
        raw = _msg(_multipart(
            "mixed",
            _multipart("alternative", PLAIN.format("P"), HTML.format("<p>H</p>"), boundary="a"),
            PDF.format(params="", disp='Content-Disposition: attachment; filename="f.pdf"\r\n'),
        ))
        result = parse_email(raw, body_format="full")
        assert result["body_plain"].strip() == "P"
        assert result["body_html"].strip() == "<p>H</p>"
        assert [a["filename"] for a in result["attachments"]] == ["f.pdf"]

    def test_inline_plain_parts_are_joined(self):
        raw = _msg(_multipart(
            "mixed", PLAIN.format("Del 1"),
            'Content-Type: image/png\r\nContent-Disposition: inline; filename="b.png"\r\n\r\nPNG',
            PLAIN.format("Del 2"),
        ))
        result = parse_email(raw, body_format="full")
        assert "Del 1" in result["body_plain"] and "Del 2" in result["body_plain"]

    def test_forwarded_message_attachments_not_listed(self):
        inner = _multipart(
            "mixed", PLAIN.format("Inre"),
            PDF.format(params="", disp='Content-Disposition: attachment; filename="inre.pdf"\r\n'),
            boundary="i",
        )
        raw = _msg(_multipart(
            "mixed", PLAIN.format("Yttre"),
            "Content-Type: message/rfc822\r\n\r\nFrom: c@d.se\r\nSubject: inre\r\n" + inner,
        ))
        result = parse_email(raw, body_format="full")
        assert result["body_plain"].strip() == "Yttre"
        assert [a["content_type"] for a in result["attachments"]] == ["message/rfc822"]

    def test_single_part_pdf_is_attachment_not_body(self):
        raw = _msg(PDF.format(params='; name="scan.pdf"', disp=""))
        result = parse_email(raw, body_format="full")
        assert result["body_plain"] == ""
        assert result["attachments"] == [
            {"filename": "scan.pdf", "content_type": "application/pdf", "size": 9}
        ]


class TestAttachedMessageSize:
    """PE10: ett bifogat .eml får sin verkliga storlek."""

    def test_rfc822_size_is_nonzero(self):
        raw = _msg(_multipart(
            "mixed", PLAIN.format("hej"),
            'Content-Type: message/rfc822\r\nContent-Disposition: attachment; filename="fw.eml"'
            "\r\n\r\nFrom: c@d.se\r\nSubject: inre\r\n\r\nInre text som är lång nog",
        ))
        (att,) = parse_email(raw)["attachments"]
        assert att["filename"] == "fw.eml"
        assert att["size"] > len("Inre text som är lång nog")


class TestWhitespaceOnlyPlainFallsBackToHtml:
    """PE12: en textdel med bara blanktecken stänger inte av HTML-fallbacken."""

    @pytest.mark.parametrize("fmt", ["text", "stripped"])
    @pytest.mark.parametrize("plain", [" ", "\r\n", " \r\n \t"])
    def test_fallback(self, fmt, plain):
        result = parse_email(_alternative(plain, "<p>Riktigt innehåll</p>"), body_format=fmt)
        assert "Riktigt innehåll" in result["body_plain"]

    def test_full_mode_keeps_raw_plain(self):
        result = parse_email(_alternative(" ", "<p>H</p>"), body_format="full")
        assert result["body_plain"].strip() == ""

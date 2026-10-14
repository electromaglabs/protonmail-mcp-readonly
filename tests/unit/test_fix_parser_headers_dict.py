"""headers-dicten och trådrubriker (PE15)."""
import pytest

from protonmail_mcp.email_parser import parse_email


def _mail(extra: str) -> bytes:
    return f"From: a@b.se\r\nSubject: s\r\n{extra}\r\n\r\nbody\r\n".encode()


class TestHeaderNamesAreCanonical:
    """Givet ett mejl där välkända rubriker har annat skiftläge
    När det parsas
    Så har headers-dicten den vedertagna stavningen, så att uppslag som
    headers["References"] fungerar oavsett hur avsändaren stavade."""

    @pytest.mark.parametrize("name", ["references", "REFERENCES", "rEfErEnCeS"])
    def test_references_any_case(self, name):
        r = parse_email(_mail(f"{name}: <a@x.se> <b@x.se>"))
        assert r["headers"]["References"] == "<a@x.se> <b@x.se>"
        assert name not in r["headers"] or name == "References"

    def test_message_id_canonical(self):
        r = parse_email(_mail("message-id: <m@x.se>"))
        assert r["headers"]["Message-ID"] == "<m@x.se>"
        assert r["message_id"] == "<m@x.se>"

    def test_unknown_header_keeps_first_spelling(self):
        r = parse_email(_mail("X-PM-Origin: internal\r\nx-pm-origin: external"))
        assert r["headers"]["X-PM-Origin"] == "internal"
        assert "x-pm-origin" not in r["headers"]

    def test_duplicates_keep_first_occurrence(self):
        r = parse_email(_mail("References: <first@x.se>\r\nreferences: <second@x.se>"))
        assert r["headers"]["References"] == "<first@x.se>"


class TestThreadingKeys:
    """parse_email exponerar in_reply_to och references direkt."""

    def test_present(self):
        r = parse_email(_mail("In-Reply-To: <p@x.se>\r\nREFERENCES: <a@x.se>\r\n <p@x.se>"))
        assert r["in_reply_to"] == "<p@x.se>"
        assert r["references"] == "<a@x.se> <p@x.se>"

    def test_absent(self):
        r = parse_email(_mail("X: y"))
        assert r["in_reply_to"] == "" and r["references"] == ""

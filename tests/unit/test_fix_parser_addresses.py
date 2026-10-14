"""Adressrubriker: avkodade namn och citering (PE6, PE7)."""
from email.utils import parseaddr

import pytest

from protonmail_mcp.email_parser import extract_addresses, parse_email


def _mail(headers: str) -> bytes:
    return f"{headers}\r\nSubject: s\r\n\r\nbody\r\n".encode()


class TestEncodedNamesInAddressLists:
    """PE6: namn i To/Cc/Bcc/Reply-To avkodas som i From."""

    def test_to_cc_reply_to_names_are_decoded(self):
        r = parse_email(_mail(
            "From: a@b.se\r\nTo: =?utf-8?q?Gr=C3=B6n?= <g@x.se>\r\n"
            "Cc: =?utf-8?b?w4VzYQ==?= <asa@x.se>\r\nReply-To: =?utf-8?q?Sv=C3=A4r?= <r@x.se>"
        ))
        assert r["to"] == ["Grön <g@x.se>"]
        assert r["cc"] == ["Åsa <asa@x.se>"]
        assert r["reply_to"] == ["Svär <r@x.se>"]

    def test_encoded_comma_does_not_split_recipient(self):
        r = parse_email(_mail("From: a@b.se\r\nTo: =?utf-8?q?Doe=2C_John?= <j@x.se>, k@x.se"))
        assert r["to"] == ['"Doe, John" <j@x.se>', "k@x.se"]

    def test_extract_addresses_decodes_names(self):
        assert extract_addresses("=?utf-8?q?Gr=C3=B6n?= <g@x.se>") == ["Grön <g@x.se>"]

    def test_folded_address_list(self):
        r = parse_email(_mail("From: a@b.se\r\nTo: a@x.se,\r\n =?utf-8?q?B=C3=B6?= <b@x.se>"))
        assert r["to"] == ["a@x.se", "Bö <b@x.se>"]


class TestFromIsReplyable:
    """PE7: from formateras så att det går att skicka tillbaka som adress."""

    @pytest.mark.parametrize(
        "raw_from, name, addr",
        [
            ("=?utf-8?q?=C3=96berg=2C_=C3=85sa?= <asa@x.se>", "Öberg, Åsa", "asa@x.se"),
            ('"Doe, John" <john@x.se>', "Doe, John", "john@x.se"),
            ("=?utf-8?q?boss=40corp=2Ecom_=3Cevil=40attacker=2Eexample=3E?= <real@corp.com>",
             "boss@corp.com <evil@attacker.example>", "real@corp.com"),
            ('=?utf-8?q?a=22b?= <x@y.se>', 'a"b', "x@y.se"),
        ],
    )
    def test_from_roundtrips_through_parseaddr(self, raw_from, name, addr):
        r = parse_email(_mail(f"From: {raw_from}"))
        assert parseaddr(r["from"]) == (name, addr)
        assert r["addresses"]["from"] == [[name, addr]]

    def test_plain_from_unchanged(self):
        assert parse_email(_mail("From: sender@example.com"))["from"] == "sender@example.com"
        assert parse_email(_mail("From: John Doe <j@x.se>"))["from"] == "John Doe <j@x.se>"

    def test_unparseable_from_falls_back_to_decoded_text(self):
        r = parse_email(_mail("From: =?utf-8?q?Bara_ett_namn?="))
        assert r["from"] == "Bara ett namn"

    def test_addresses_key_has_all_lists(self):
        r = parse_email(_mail("From: a@b.se\r\nTo: =?utf-8?q?Gr=C3=B6n?= <g@x.se>"))
        assert r["addresses"] == {
            "from": [["", "a@b.se"]],
            "to": [["Grön", "g@x.se"]],
            "cc": [],
            "bcc": [],
            "reply_to": [],
        }


class TestNoParserDifferential:
    """Givet en adressrubrik där kodade ord försöker skapa en annan adress
    När den parsas
    Så avkodas bara visningsnamnet — aldrig adressdelen — och varje
    formaterad adress parsas tillbaka till exakt det par som rapporteras."""

    NASTY = [
        "x <=?utf-8?q?evil=40a.com=3E_=3Creal?=@b.com>",
        "x <a@b.se>, =?utf-8?q?evil=40a.com?=",
        "=?utf-8?q?a=5C=22_=3Cevil=40x=3E?= <ok@b.se>",
        '"a\\" <evil@x>" <ok@b.se>',
        "=?utf-8?q?Gr=C3=B6n=0D=0ABcc=3A_evil=40x?= <g@x.se>",
    ]

    @pytest.mark.parametrize("value", NASTY)
    def test_encoded_words_never_become_an_address(self, value):
        r = parse_email(_mail(f"From: {value}\r\nTo: {value}"))
        for _, addr in r["addresses"]["to"]:
            assert addr != "evil@a.com" and not addr.startswith("evil@")

    @pytest.mark.parametrize("value", NASTY)
    def test_formatted_addresses_roundtrip(self, value):
        r = parse_email(_mail(f"From: {value}\r\nTo: {value}"))
        for formatted, (name, addr) in zip(r["to"], r["addresses"]["to"]):
            assert "\r" not in formatted and "\n" not in formatted
            if addr and "@" in addr:
                assert parseaddr(formatted)[1] == addr


class TestNoRecipientInjection:
    """Givet en adressrubrik vars kodade ord avkodas till flera adresser
    När from/to formateras
    Så kan strängen aldrig parsas till andra adresser än de som faktiskt
    stod i rubrikens adressdel (reply_to_email skickar till "from")."""

    NASTY = TestNoParserDifferential.NASTY + [
        "=?utf-8?q?a=40x.se=2C_evil=40y.se?=",
        "=?utf-8?q?a=40x.se=2C_evil=40y.se?= <>",
        "=?utf-8?q?evil=40y.se?=",
    ]

    @staticmethod
    def _parsed(value):
        from email.utils import getaddresses

        return {addr for _, addr in getaddresses([value]) if addr}

    @pytest.mark.parametrize("value", NASTY)
    def test_from_and_to_only_contain_real_addresses(self, value):
        r = parse_email(_mail(f"From: {value}\r\nTo: {value}"))
        real = {addr for _, addr in r["addresses"]["from"]}
        assert self._parsed(r["from"]) <= real
        for formatted in r["to"]:
            assert len(self._parsed(formatted)) <= 1
            assert self._parsed(formatted) <= real
        assert "evil@y.se" not in self._parsed(r["from"])

"""K7: mappnamn i modified UTF-7 (RFC 3501 §5.1.3) avkodas i LIST och kodas vid sändning."""
import pytest

from protonmail_mcp.imap_client import _parse_list_line, _quote_mailbox
from protonmail_mcp.mailbox_names import decode_modified_utf7, encode_modified_utf7

# (läsbart namn, namn på tråden) — kontrollerade mot RFC 3501 och mot Bridge live
CASES = [
    ("INBOX", "INBOX"),
    ("", ""),
    ("Labels/Näs Samfällighet", "Labels/N&AOQ-s Samf&AOQ-llighet"),
    ("Labels/Släktforskning", "Labels/Sl&AOQ-ktforskning"),
    ("Labels/Grönvik", "Labels/Gr&APY-nvik"),
    ("Labels/Stenungsunds OK-gula spåret", "Labels/Stenungsunds OK-gula sp&AOU-ret"),
    ("ÅÄÖ åäö", "&AMUAxADW- &AOUA5AD2-"),
    ("&", "&-"),
    ("R&D", "R&-D"),
    ("&&", "&-&-"),
    ("Smörgås & bröd", "Sm&APY-rg&AOU-s &- br&APY-d"),
    ("~peter/mail/台北/日本語", "~peter/mail/&U,BTFw-/&ZeVnLIqe-"),  # exemplet i RFC 3501
    ("😀", "&2D3eAA-"),  # U+1F600, surrogatpar D83D DE00
    ("Fest 🎉🎂", "Fest &2Dzfidg834I-"),
    ("é😀ä", "&AOnYPd4AAOQ-"),  # BMP + surrogatpar + BMP i samma base64-sekvens
    ("a-b_c.d", "a-b_c.d"),
    ("Labels/Neomeda\\/Kvitto", "Labels/Neomeda\\/Kvitto"),
]


class TestEncode:
    @pytest.mark.parametrize("readable,wire", CASES)
    def test_encode(self, readable, wire):
        assert encode_modified_utf7(readable) == wire

    def test_lone_surrogate_rejected(self):
        with pytest.raises(ValueError):
            encode_modified_utf7("x\ud800y")

    def test_output_is_printable_ascii(self):
        wire = encode_modified_utf7("Nyhetsbrev – Klimat 🌍 ×")
        assert all(0x20 <= ord(c) <= 0x7E for c in wire)


class TestDecode:
    @pytest.mark.parametrize("readable,wire", CASES)
    def test_decode(self, readable, wire):
        assert decode_modified_utf7(wire) == readable

    @pytest.mark.parametrize(
        "wire",
        [
            "&AOQ",          # saknar avslutande "-"
            "a&",            # saknar avslutande "-"
            "&AOQ-&AOQ-",    # två intilliggande sekvenser ska vara en (inte kanonisk)
            "&AGE-",         # "a" får inte base64-kodas
            "&ACY-",         # "&" ska skrivas "&-"
            "&AOR-",         # utfyllnadsbitar som inte är noll
            "&Jjo!-",        # ogiltigt tecken i base64
            "&AOQA-",        # udda antal byte
            "&A-",           # omöjlig base64-längd
            "&2D0-",         # ensam hög surrogat
            "&3gA-",         # ensam låg surrogat
            "&AOQ/AOQ-",     # "/" i stället för ","
            "Näs",           # rå icke-ASCII är inte modified UTF-7
            "a\tb",          # kontrolltecken
        ],
    )
    def test_invalid_rejected(self, wire):
        with pytest.raises(ValueError):
            decode_modified_utf7(wire)


@pytest.mark.parametrize(
    "readable",
    ["Näs", "&-&", "a&-b", "日本語 & 😀 &AOQ-", " ", "x" * 100 + "ö" * 100, "🎉" * 20],
)
def test_roundtrip(readable):
    assert decode_modified_utf7(encode_modified_utf7(readable)) == readable


class TestImapClientIntegration:
    def test_list_line_decoded(self):
        line = '(\\Unmarked) "/" "Labels/N&AOQ-s Samf&AOQ-llighet"'
        assert _parse_list_line(line) == "Labels/Näs Samfällighet"

    def test_list_line_with_escape_and_utf7(self):
        line = '(\\Unmarked) "/" "Labels/Sm&APY-r\\\\/Br&APY-d"'
        assert _parse_list_line(line) == "Labels/Smör\\/Bröd"

    def test_invalid_utf7_kept_raw(self):
        assert _parse_list_line('(\\Unmarked) "/" "Labels/A&B"') == "Labels/A&B"

    def test_quote_encodes(self):
        assert _quote_mailbox("Labels/Näs Samfällighet") == '"Labels/N&AOQ-s Samf&AOQ-llighet"'

    def test_quote_encodes_ampersand(self):
        assert _quote_mailbox("Folders/R&D") == '"Folders/R&-D"'

    def test_quote_encodes_and_escapes(self):
        assert _quote_mailbox('Labels/Smör\\/"Bröd"') == '"Labels/Sm&APY-r\\\\/\\"Br&APY-d\\""'

    def test_quote_rejects_lone_surrogate(self):
        with pytest.raises(ValueError, match="Ogiltigt mailbox-namn"):
            _quote_mailbox("Labels/\ud800")

    @pytest.mark.parametrize("readable,wire", CASES[2:])
    def test_list_then_quote_is_symmetric(self, readable, wire):
        escaped = wire.replace("\\", "\\\\")
        name = _parse_list_line(f'(\\Unmarked) "/" "{escaped}"')
        assert name == readable
        assert _quote_mailbox(name) == f'"{escaped}"'

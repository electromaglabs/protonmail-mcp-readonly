"""_parse_headers: blanktecken mitt i ett värde får inte ge kvadratisk tid (S5).

Mönstret \\s*\\r?\\n\\s* provar från varje blanksteg i en lång följd utan
radbrytning: 100 000 blanksteg tog 50 s. Det befintliga testet med
blanksteg direkt efter kolon fångade inte det, eftersom email-parsern
redan tar bort inledande blanktecken.
"""
import time

from protonmail_mcp.imap_client import _parse_headers


def test_blanks_inside_value_are_linear():
    raw = b"Subject: a" + b" " * 30_000 + b"b\r\n"
    start = time.perf_counter()
    result = _parse_headers(raw)
    assert time.perf_counter() - start < 0.5
    assert result["subject"] == "a" + " " * 30_000 + "b"


def test_folding_still_joins_with_one_space():
    raw = b"Subject: Hej  \r\n \t  du\r\n   \r\n  dar\r\nTo: x@y.se\r\n"
    assert _parse_headers(raw)["subject"] == "Hej du dar"

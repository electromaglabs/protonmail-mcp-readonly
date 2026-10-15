"""iso_date: RFC 5322-datum → ISO 8601 (llm-injektion)."""
import time

import pytest

from protonmail_mcp.email_parser import iso_date, parse_email


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Tue, 14 Oct 2026 21:45:52 +0200", "2026-10-14T21:45:52+02:00"),
        ("Tue, 14 Oct 2026 21:45:52 +0530", "2026-10-14T21:45:52+05:30"),
        ("Tue, 14 Oct 2026 21:45 +0200", "2026-10-14T21:45:00+02:00"),
        ("14 Oct 2026 21:45:52 UT", "2026-10-14T21:45:52+00:00"),
        ("Tue, 14 Oct 2026 21:45:52 EST", "2026-10-14T21:45:52-05:00"),
        ("Tue, 14 Oct 2026 21:45:52", "2026-10-14T21:45:52+00:00"),  # utan zon: UTC
        ("  Tue,  14  Oct  2026 21:45:52 +0200  ", "2026-10-14T21:45:52+02:00"),
    ],
)
def test_tolkas(value, expected):
    assert iso_date(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", None, "imorgon", "Tue, 32 Oct 2026 21:45:52 +0200", "Tue, 14 Foo 2026 25:61:00 +0200",
     "Tue, 14 Oct 99999 21:45:52 +0200", "0", "Tue, 14 Oct 2026 21:45:52 +9999"],
)
def test_otolkbart_ger_none(value):
    assert iso_date(value) is None


def test_langt_datum_ar_snabbt():
    start = time.perf_counter()
    iso_date("Tue, " + "1 " * 500_000)
    assert time.perf_counter() - start < 1


def test_parse_email_har_date_iso_bredvid_date():
    result = parse_email(b"From: a@b.se\r\nDate: Wed, 15 Oct 2026 08:00:00 +0200\r\n\r\nx\r\n")
    assert result["date"] == "Wed, 15 Oct 2026 08:00:00 +0200"
    assert result["date_iso"] == "2026-10-15T08:00:00+02:00"


def test_parse_email_utan_datum():
    assert parse_email(b"From: a@b.se\r\n\r\nx\r\n")["date_iso"] is None

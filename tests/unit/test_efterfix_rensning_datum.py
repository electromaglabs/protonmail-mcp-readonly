"""F12: tvåsiffriga och tresiffriga år, okänd zon, "+02" och skottsekund."""
import time

import pytest

from protonmail_mcp.email_parser import iso_date


@pytest.mark.parametrize("value,expected", [
    ("14 Oct 00 21:45 +0200", "2000-10-14T21:45:00+02:00"),
    ("14 Oct 49 21:45 +0200", "2049-10-14T21:45:00+02:00"),
    ("14 Oct 50 21:45 +0200", "1950-10-14T21:45:00+02:00"),
    ("14 Oct 68 21:45 +0200", "1968-10-14T21:45:00+02:00"),
    ("14 Oct 69 21:45 +0200", "1969-10-14T21:45:00+02:00"),
    ("14 Oct 99 21:45 +0200", "1999-10-14T21:45:00+02:00"),
    ("Tue, 14 Oct 126 21:45 +0200", "2026-10-14T21:45:00+02:00"),
    ("14 Oct 999 21:45 +0200", "2899-10-14T21:45:00+02:00"),
    ("14 Oct 2026 21:45 +0200", "2026-10-14T21:45:00+02:00"),
    ("Tuesday, 14-Oct-26 21:45:52 GMT", "2026-10-14T21:45:52+00:00"),
])
def test_ar(value, expected):
    assert iso_date(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("Tue, 14 Oct 2026 21:45:52 CEST", "2026-10-14T21:45:52"),
    ("Tue, 14 Oct 2026 21:45:52 XYZ", "2026-10-14T21:45:52"),
    ("Tue, 14 Oct 2026 21:45:52", "2026-10-14T21:45:52"),
    ("Tue, 14 Oct 2026 21:45:52 -0000", "2026-10-14T21:45:52+00:00"),
    ("Tue, 14 Oct 2026 21:45:52 +0000", "2026-10-14T21:45:52+00:00"),
    ("Tue, 14 Oct 2026 21:45:52 GMT", "2026-10-14T21:45:52+00:00"),
    ("Tue, 14 Oct 2026 21:45:52 EST", "2026-10-14T21:45:52-05:00"),
    ("Tue, 14 Oct 2026 21:45:52 +0200 (CEST)", "2026-10-14T21:45:52+02:00"),
    ("14 Oct 2026 21:45 +02", "2026-10-14T21:45:00+02:00"),
    ("14 Oct 2026 21:45 -05", "2026-10-14T21:45:00-05:00"),
    ("14 Oct 2026 21:45 +02:00", "2026-10-14T21:45:00+02:00"),
])
def test_zon(value, expected):
    assert iso_date(value) == expected


def test_skottsekund():
    assert iso_date("Thu, 31 Dec 2026 23:59:60 +0000") == "2026-12-31T23:59:59+00:00"


@pytest.mark.parametrize("value", [
    "30 Feb 2026 10:00 +0000", "14 Oct 2026 25:00 +0000", "14 Oct 2026 21:45 +2400",
    "14 Oct 10000 21:45 +0000", "14 Oct 2026 21:45:61 +0000", "14 Oct 2026",
])
def test_ogiltigt_ger_none(value):
    assert iso_date(value) is None


def test_langt_datum_ar_snabbt():
    start = time.perf_counter()
    iso_date("Tue, 14 Oct " + "9" * 150 + " 21:45 +02")
    assert time.perf_counter() - start < 0.5

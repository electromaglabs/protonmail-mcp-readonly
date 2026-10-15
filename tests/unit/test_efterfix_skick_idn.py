"""IDN-domäner normaliseras enligt IDNA2008/UTS46 (non-transitional), inte IDNA2003.

Pythons codec "idna" följer IDNA2003 och skriver om ß→ss och ς→σ, så
straße.de blev strasse.de — en annan registrerad domän (granskning 3, policy F1).
"""
import pytest

from protonmail_mcp.config import normalize_domain, parse_allowed_recipients
from protonmail_mcp.smtp_client import _to_address


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("straße.de", "xn--strae-oqa.de"),
        ("faß.de", "xn--fa-hia.de"),
        ("σόλος.gr", "xn--wxaijb9b.gr"),
        ("EXÄMPLE.se", "xn--exmple-cua.se"),
        ("exempel.se", "exempel.se"),
    ],
)
def test_normalize_domain_uses_idna2008(domain, expected):
    assert normalize_domain(domain) == expected


def test_allowed_recipients_keep_sharp_s_domain():
    assert parse_allowed_recipients("@straße.de") == (("", "xn--strae-oqa.de"),)


@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        ("info@straße.de", "info@xn--strae-oqa.de"),
        ("info@σόλος.gr", "info@xn--wxaijb9b.gr"),
        ("Anna <anna@Bücher.example>", "anna@xn--bcher-kva.example"),
    ],
)
def test_to_address_uses_idna2008(addr, expected):
    assert _to_address(addr).addr_spec == expected


def test_to_address_rejects_invalid_idn_domain_with_value_error():
    with pytest.raises(ValueError, match="Ogiltig e-postadress"):
        _to_address("x@exämple..se")


def test_normalize_domain_invalid_idn_is_none():
    assert normalize_domain("ex_ämple.se") is None

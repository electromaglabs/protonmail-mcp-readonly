"""Adresser som klarar mönstret men får email.headerregistry att kasta
(HeaderParseError) ska ge ValueError "Ogiltig e-postadress" (granskning 3, policy F4)."""
import pytest

from protonmail_mcp.smtp_client import _to_address, _validate_email_addr, prepared_recipients
from protonmail_mcp.tools._errors import describe_error

BROKEN = ['"<hemlig.chef\\"@firma.se', '"a\\"@firma.se']


@pytest.mark.parametrize("addr", BROKEN)
def test_validate_rejects_address_that_address_cannot_build(addr):
    with pytest.raises(ValueError, match="Ogiltig e-postadress") as exc:
        _validate_email_addr(addr)
    # Inget kedjat HeaderParseError med adressen i ett eventuellt stackspår
    assert exc.value.__cause__ is None
    assert exc.value.__suppress_context__


@pytest.mark.parametrize("addr", BROKEN)
def test_to_address_raises_value_error(addr):
    with pytest.raises(ValueError, match="Ogiltig e-postadress"):
        _to_address(addr)


def test_error_reaches_client_as_invalid_address_not_unexpected():
    with pytest.raises(ValueError) as exc:
        _validate_email_addr(BROKEN[0])
    text = describe_error(exc.value, tool_name="send_email", open_world=True)
    assert text.startswith("Ogiltig e-postadress")


def test_valid_quoted_addresses_still_pass():
    assert _validate_email_addr('"a,b"@exempel.se')
    assert _to_address('"a,b"@exempel.se').addr_spec == '"a,b"@exempel.se'


def test_prepared_recipients_rejects_broken_display_parse():
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["To"] = "a@b.se"
    msg.set_content("x")
    # Rubriken sätts rått: email.policy skulle annars vägra den redan här
    msg._headers.append(("Bcc", '"<hemlig.chef\\"@firma.se'))
    with pytest.raises(ValueError):
        prepared_recipients(msg)

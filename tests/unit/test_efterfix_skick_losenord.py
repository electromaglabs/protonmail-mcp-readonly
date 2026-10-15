"""_scrub maskerar lösenordet även URL-kodat, efter blankstegsnormalisering
och före kapning (granskning 3, policy F5 — härdning)."""
from types import SimpleNamespace
from urllib.parse import quote, quote_plus

import aiosmtplib
import pytest

from protonmail_mcp import config
from protonmail_mcp.smtp_client import SMTPPartialDeliveryError
from protonmail_mcp.tools import _errors

PW = "hemligt  lösen/ord+1"


@pytest.fixture(autouse=True)
def password(monkeypatch):
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(password=PW))


def _describe(exc, open_world=False):
    return _errors.describe_error(exc, tool_name="t", open_world=open_world)


def _clean(text):
    return "hemligt" not in text and "sen/ord" not in text and "sen%2Ford" not in text


@pytest.mark.parametrize("form", [PW, quote(PW, safe=""), quote(PW), quote_plus(PW), " ".join(PW.split())])
def test_scrub_masks_all_forms(form):
    assert _clean(_errors._scrub(f"fel: {form} slut"))


def test_detail_masks_after_whitespace_collapse():
    assert _clean(_describe(ConnectionError(f"fel {PW}")))


def test_detail_masks_before_clipping():
    text = "x" * (_errors._MAX_DETAIL_CHARS - 12) + " " + PW  # kapas mitt i lösenordet
    assert _clean(_describe(ConnectionError(text)))


def test_smtp_reply_masks_collapsed_password():
    exc = aiosmtplib.SMTPResponseException(554, f"rejected {PW}")
    assert _clean(_describe(exc, open_world=True))


def test_smtp_auth_reply_masks_collapsed_password():
    exc = aiosmtplib.SMTPAuthenticationError(535, f"bad credentials {PW}")
    assert _clean(_describe(exc))


def test_partial_delivery_masks_collapsed_password():
    exc = SMTPPartialDeliveryError(refused={"b@x.se": (550, f"nej {PW}")}, delivered=["a@x.se"])
    assert _clean(_describe(exc, open_world=True))


def test_unexpected_error_log_masks_url_encoded_password(caplog):
    try:
        raise RuntimeError(f"oops {quote(PW, safe='')}")
    except RuntimeError as exc:
        _describe(exc)
    assert _clean(caplog.text)


def test_text_without_password_is_unchanged():
    assert _errors._scrub("vanligt fel") == "vanligt fel"

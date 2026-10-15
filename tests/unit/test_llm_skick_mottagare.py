"""PROTONMAIL_ALLOWED_RECIPIENTS: tolkning av listan och jämförelsen."""
import email
import email.policy

import pytest
from pydantic import ValidationError

from protonmail_mcp import policy
from protonmail_mcp.smtp_client import SMTPClient
from tests.llm_skick_support import BridgeSpy, make_settings, record_smtp, spy_smtp_patch


def test_default_allows_everyone():
    settings = make_settings()
    assert settings.allowed_recipients == ""
    policy.check_recipients(settings, ["vem@som.helst"])  # kastar inte


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("@exempel.se", (("", "exempel.se"),)),
        (" @Exempel.SE , Anna@Firma.SE ", (("", "exempel.se"), ("Anna", "firma.se"))),
        ("@exämple.se", (("", "xn--exmple-cua.se"),)),
        ("bo@EXÄMPLE.se", (("bo", "xn--exmple-cua.se"),)),
        ("a@b.se,,", (("a", "b.se"),)),
    ],
)
def test_parse_rules(raw, expected):
    assert policy.parse_allowed_recipients(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["inte en adress", "@", "a@", "@exempel", "a@@b.se", "a b@c.se", "@exem pel.se", "a@b..se", "@-.se"],
)
def test_invalid_entries_rejected_at_startup(raw):
    with pytest.raises(ValidationError):
        make_settings(allowed_recipients=raw)


@pytest.mark.parametrize(
    "rules, address, allowed",
    [
        ("@exempel.se", "anna@exempel.se", True),
        ("@exempel.se", "anna@EXEMPEL.SE", True),
        ("@exempel.se", "anna@sub.exempel.se", False),
        ("@exempel.se", "anna@exempel.se.ond.example", False),
        ("@exempel.se", "anna@xexempel.se", False),
        ("bo@exempel.se", "bo@exempel.se", True),
        ("bo@exempel.se", "bo@EXEMPEL.se", True),
        ("bo@exempel.se", "Bo@exempel.se", False),
        ("bo@exempel.se", "bob@exempel.se", False),
        ("bo@exempel.se", "xbo@exempel.se", False),
        ("@exämple.se", "a@xn--exmple-cua.se", True),
        ("@xn--exmple-cua.se", "a@exämple.se", True),
        ("@exämple.se", "a@EXÄMPLE.SE", True),
    ],
)
def test_matching(rules, address, allowed):
    settings = make_settings(allowed_recipients=rules)
    if allowed:
        policy.check_recipients(settings, [address])
    else:
        with pytest.raises(ValueError, match="PROTONMAIL_ALLOWED_RECIPIENTS"):
            policy.check_recipients(settings, [address])


def test_error_lists_every_refused_address_once():
    settings = make_settings(allowed_recipients="@exempel.se")
    with pytest.raises(ValueError) as exc:
        policy.check_recipients(settings, ["a@exempel.se", "x@ond.example", "y@ond.example", "x@ond.example"])
    text = str(exc.value)
    assert "x@ond.example, y@ond.example" in text
    assert text.count("x@ond.example") == 1
    assert "a@exempel.se" not in text


async def test_send_email_refused_before_smtp():
    spy = BridgeSpy()
    smtp = SMTPClient(make_settings(allowed_recipients="@exempel.se"))
    with spy_smtp_patch(spy), pytest.raises(ValueError, match="ond@annat.se"):
        await smtp.send_email(to="anna@exempel.se", bcc=["ond@annat.se"], subject="Hej", body="Hej")
    assert spy.smtp_connections == 0


async def test_send_prepared_message_checks_bcc():
    spy = BridgeSpy()
    smtp = SMTPClient(make_settings(allowed_recipients="@exempel.se"))
    raw = (
        "From: me@proton.me\r\nTo: anna@exempel.se\r\nBcc: ond@annat.se\r\n"
        "Subject: Hej\r\n\r\nHej\r\n"
    ).encode()
    msg = email.message_from_bytes(raw, policy=email.policy.SMTP)
    with spy_smtp_patch(spy), pytest.raises(ValueError, match="ond@annat.se"):
        await smtp.send_prepared_message(msg)
    assert spy.smtp_connections == 0


async def test_send_prepared_message_allowed():
    spy = BridgeSpy()
    smtp = SMTPClient(make_settings(allowed_recipients="@exempel.se"))
    raw = "From: me@proton.me\r\nTo: anna@exempel.se\r\nSubject: Hej\r\n\r\nHej\r\n".encode()
    msg = email.message_from_bytes(raw, policy=email.policy.SMTP)
    with record_smtp(spy) as captured:
        assert await smtp.send_prepared_message(msg) is True
    assert captured.recipients == ["anna@exempel.se"]


def test_from_environment(monkeypatch):
    from protonmail_mcp.config import Settings

    monkeypatch.setenv("PROTONMAIL_ALLOWED_RECIPIENTS", "@exempel.se,chef@firma.se")
    settings = Settings(username="u", password="p", _env_file=None)
    assert policy.parse_allowed_recipients(settings.allowed_recipients) == (
        ("", "exempel.se"), ("chef", "firma.se"),
    )

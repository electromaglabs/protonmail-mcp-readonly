"""PROTONMAIL_MAX_RECIPIENTS och PROTONMAIL_MAX_SENDS_PER_HOUR."""
import pytest
from pydantic import ValidationError

from protonmail_mcp import policy
from protonmail_mcp.smtp_client import SMTPClient
from tests.llm_skick_support import BridgeSpy, make_settings, record_smtp


class Clock:
    def __init__(self, now: float = 5000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_defaults():
    settings = make_settings()
    assert settings.max_recipients == 50
    assert settings.max_sends_per_hour == 30


@pytest.mark.parametrize("key", ["max_recipients", "max_sends_per_hour"])
def test_negative_rejected(key):
    with pytest.raises(ValidationError):
        make_settings(**{key: -1})


def test_recipient_count_counts_unique_addresses_case_insensitively():
    settings = make_settings(max_recipients=2)
    policy.check_recipient_count(settings, ["a@x.se", "A@X.SE", "b@x.se"])  # två unika
    with pytest.raises(ValueError, match="3 mottagare.*högst 2"):
        policy.check_recipient_count(settings, ["a@x.se", "b@x.se", "c@x.se"])


def test_zero_recipients_limit_means_unlimited():
    policy.check_recipient_count(make_settings(max_recipients=0), [f"m{i}@x.se" for i in range(500)])


def test_rate_limiter_sliding_window():
    clock = Clock()
    limiter = policy.SendRateLimiter(clock)
    settings = make_settings(max_sends_per_hour=2)
    limiter.acquire(settings)
    clock.now += 600
    limiter.acquire(settings)
    clock.now += 600
    with pytest.raises(ValueError, match="PROTONMAIL_MAX_SENDS_PER_HOUR") as exc:
        limiter.acquire(settings)
    assert "om 40 minuter" in str(exc.value)
    clock.now += 40 * 60  # det första skicket är nu exakt en timme gammalt
    limiter.acquire(settings)
    with pytest.raises(ValueError, match="om 10 minuter"):
        limiter.acquire(settings)


def test_rate_limiter_rounds_wait_up_and_says_seconds_when_short():
    clock = Clock()
    limiter = policy.SendRateLimiter(clock)
    settings = make_settings(max_sends_per_hour=1)
    limiter.acquire(settings)
    clock.now += 3600 - 30
    with pytest.raises(ValueError, match="om 30 sekunder"):
        limiter.acquire(settings)
    clock.now += 29.5
    with pytest.raises(ValueError, match="om 1 sekund"):
        limiter.acquire(settings)


def test_rate_limiter_message_has_clock_time():
    clock = Clock()
    limiter = policy.SendRateLimiter(clock)
    settings = make_settings(max_sends_per_hour=1)
    limiter.acquire(settings)
    with pytest.raises(ValueError, match=r"kl\. \d\d:\d\d"):
        limiter.acquire(settings)


def test_rate_limit_zero_means_unlimited():
    limiter = policy.SendRateLimiter(Clock())
    settings = make_settings(max_sends_per_hour=0)
    for _ in range(100):
        limiter.acquire(settings)


async def test_smtp_client_uses_one_counter_for_all_paths():
    """send_email och send_prepared_message delar räknaren (båda går genom _deliver)."""
    import email
    import email.policy

    spy = BridgeSpy()
    smtp = SMTPClient(make_settings(max_sends_per_hour=2))
    smtp._clock = Clock()
    raw = "From: me@proton.me\r\nTo: anna@exempel.se\r\nSubject: Hej\r\n\r\nHej\r\n".encode()
    with record_smtp(spy) as captured:
        await smtp.send_email(to="anna@exempel.se", subject="Hej", body="Hej")
        await smtp.send_prepared_message(email.message_from_bytes(raw, policy=email.policy.SMTP))
        with pytest.raises(ValueError, match="PROTONMAIL_MAX_SENDS_PER_HOUR"):
            await smtp.send_email(to="anna@exempel.se", subject="Hej", body="Hej")
    assert len(captured.sent) == 2
    assert spy.smtp_connections == 2


async def test_too_many_recipients_does_not_consume_quota():
    spy = BridgeSpy()
    smtp = SMTPClient(make_settings(max_sends_per_hour=1, max_recipients=1))
    smtp._clock = Clock()
    with record_smtp(spy) as captured:
        with pytest.raises(ValueError, match="PROTONMAIL_MAX_RECIPIENTS"):
            await smtp.send_email(to=["a@x.se", "b@x.se"], subject="Hej", body="Hej")
        await smtp.send_email(to="a@x.se", subject="Hej", body="Hej")
    assert len(captured.sent) == 1


async def test_smtp_failure_still_counts():
    """Ett skick som nådde SMTP räknas även om det misslyckades — en loop som
    försöker om och om igen ska också stoppas."""
    from unittest.mock import patch

    smtp = SMTPClient(make_settings(max_sends_per_hour=1))
    smtp._clock = Clock()
    with patch("protonmail_mcp.smtp_client.aiosmtplib.SMTP", side_effect=OSError("nere")):
        with pytest.raises(OSError):
            await smtp.send_email(to="a@x.se", subject="Hej", body="Hej")
        with pytest.raises(ValueError, match="PROTONMAIL_MAX_SENDS_PER_HOUR"):
            await smtp.send_email(to="a@x.se", subject="Hej", body="Hej")

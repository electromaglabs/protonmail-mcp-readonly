"""Testverktyg för fix-svar: fångar SMTP-trafiken utan nätverk.

Den riktiga SMTPClient används, men aiosmtplib.SMTP byts mot en attrapp som
sparar meddelandet och mottagarlistan. Meddelandet serialiseras med samma
kod som aiosmtplib använder (flatten_message) och parsas tillbaka, så att
testerna ser exakt det som skulle ha gått ut på tråden.
"""
from __future__ import annotations

import email
import email.policy
from contextlib import contextmanager
from email.message import EmailMessage, Message
from unittest.mock import AsyncMock, MagicMock, patch

import aiosmtplib
from aiosmtplib.email import flatten_message

from protonmail_mcp.config import Settings
from protonmail_mcp.smtp_client import SMTPClient

KONTO = "me@proton.me"


def make_settings(username: str = KONTO) -> Settings:
    return Settings(username=username, password="pw", _env_file=None)


def make_client(username: str = KONTO) -> SMTPClient:
    return SMTPClient(make_settings(username))


class CapturedSMTP:
    """Sparar det som skickas och kan låtas vägra enskilda mottagare."""

    def __init__(self) -> None:
        self.sent: list[tuple[Message, list[str]]] = []
        # adress -> (kod, meddelande) för mottagare som servern ska vägra
        self.refused: dict[str, tuple[int, str]] = {}

    async def send_message(self, message, recipients=None, **_kwargs):
        recipients = list(recipients or [])
        errors = {
            r: aiosmtplib.SMTPResponse(*self.refused[r])
            for r in recipients
            if r in self.refused
        }
        if errors and len(errors) == len(recipients):
            raise aiosmtplib.SMTPRecipientsRefused(
                [
                    aiosmtplib.SMTPRecipientRefused(resp.code, resp.message, r)
                    for r, resp in errors.items()
                ]
            )
        self.sent.append((message, recipients))
        return errors, "OK"

    @property
    def message(self) -> Message:
        return self.sent[-1][0]

    @property
    def recipients(self) -> list[str]:
        return self.sent[-1][1]

    @property
    def raw(self) -> bytes:
        return flatten_message(self.message)

    @property
    def parsed(self) -> EmailMessage:
        return email.message_from_bytes(self.raw, policy=email.policy.default)


@contextmanager
def capture_smtp():
    captured = CapturedSMTP()
    instance = MagicMock()
    instance.login = AsyncMock()
    instance.send_message = AsyncMock(side_effect=captured.send_message)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=instance)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch("protonmail_mcp.smtp_client.aiosmtplib.SMTP", return_value=cm):
        yield captured


def header_addresses(msg: EmailMessage, name: str) -> list[tuple[str, str]]:
    """(display_name, addr_spec) för alla adresser i en header."""
    header = msg[name]
    if header is None:
        return []
    return [(a.display_name, a.addr_spec) for a in header.addresses]

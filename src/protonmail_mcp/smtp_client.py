import email.policy
import logging
import re
import ssl
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from typing import Sequence

import aiosmtplib

from .config import Settings

logger = logging.getLogger(__name__)


_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _validate_email_addr(addr: str) -> str:
    """Kastar ValueError om adressen innehåller CRLF eller är ogiltig."""
    if '\r' in addr or '\n' in addr:
        raise ValueError(f"Ogiltig e-postadress (CRLF): {addr!r}")
    _, parsed = parseaddr(addr)
    if not parsed or not _EMAIL_RE.match(parsed):
        raise ValueError(f"Ogiltig e-postadress: {addr!r}")
    return addr


def _to_address(addr: str) -> Address:
    """Gör om en (validerad) adressträng till ett Address-objekt.

    Display-namnet behålls som text så att policyn kan RFC 2047-koda just
    namnet; själva adressen får aldrig kodas. En IDN-domän skrivs om till
    punycode så att både header och RCPT TO blir ren ASCII.
    """
    name, spec = parseaddr(addr)
    local, _, domain = spec.rpartition("@")
    if not domain.isascii():
        try:
            domain = domain.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"Ogiltig e-postadress (domän): {addr!r}") from exc
    return Address(display_name=name, addr_spec=f"{local}@{domain}")


def _validate_subject(subject: str) -> str:
    """Kastar ValueError om ämnesraden innehåller CRLF eller är för lång."""
    if '\r' in subject or '\n' in subject:
        raise ValueError("Ämnesraden får inte innehålla radbrytningar")
    if len(subject) > 998:
        raise ValueError("Ämnesraden är för lång (max 998 tecken)")
    return subject


def _normalize_recipients(value: str | Sequence[str] | None) -> list[str]:
    """Normalize a recipient field (to/cc/bcc) to a flat list of addresses."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _build_message(
    *,
    from_addr: str,
    to_list: list[str],
    subject: str,
    body: str,
    body_html: str | None = None,
    cc_list: list[str] | None = None,
    reply_to: str | None = None,
    additional_headers: dict[str, str] | None = None,
) -> EmailMessage:
    """Build a MIME message without requiring an SMTP connection.

    Byggs med den moderna policyn (email.policy.SMTP): den kodar bara
    display-namn med icke-ASCII-tecken, aldrig hela adressheadern.
    """
    msg = EmailMessage(policy=email.policy.SMTP)
    msg.set_content(body)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    sender = _to_address(from_addr)
    msg["From"] = sender
    # To är valfri enligt RFC 5322, men får inte vara tom om den finns
    if to_list:
        msg["To"] = [_to_address(a) for a in to_list]
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    # Utan domain använder make_msgid() maskinens värdnamn (getfqdn), vilket
    # läcker det lokala nätets namn till mottagarna
    msg["Message-ID"] = make_msgid(domain=sender.domain or "localhost")
    if cc_list:
        msg["Cc"] = [_to_address(a) for a in cc_list]
    if reply_to:
        msg["Reply-To"] = _to_address(reply_to)
    if additional_headers:
        for key, value in additional_headers.items():
            msg[key] = value

    return msg


class SMTPClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False

        if settings.verify_ssl and settings.smtp_ca_cert:
            # Pinna Bridge-certifikatet
            self._ssl_ctx.verify_mode = ssl.CERT_REQUIRED
            self._ssl_ctx.load_verify_locations(cafile=settings.smtp_ca_cert)
        elif settings.verify_ssl:
            self._ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        else:
            # Standard Bridge-läge: self-signed cert
            self._ssl_ctx.verify_mode = ssl.CERT_NONE

    async def send_email(
        self,
        to: str | Sequence[str],
        subject: str,
        body: str,
        body_html: str | None = None,
        cc: str | Sequence[str] | None = None,
        bcc: str | Sequence[str] | None = None,
        reply_to: str | None = None,
        additional_headers: dict[str, str] | None = None,
    ) -> bool:
        _validate_subject(subject)

        to_list = _normalize_recipients(to)
        cc_list = _normalize_recipients(cc)
        bcc_list = _normalize_recipients(bcc)

        for addr in to_list + cc_list + bcc_list:
            _validate_email_addr(addr)
        if reply_to:
            _validate_email_addr(reply_to)

        msg = _build_message(
            from_addr=self._settings.username,
            to_list=to_list,
            subject=subject,
            body=body,
            body_html=body_html,
            cc_list=cc_list,
            reply_to=reply_to,
            additional_headers=additional_headers,
        )

        # RCPT TO får bara den nakna adressen (med punycode-domän)
        all_recipients = [
            _to_address(a).addr_spec for a in to_list + cc_list + bcc_list
        ]

        logger.info(
            "Skickar e-post (%d mottagare) via SMTP %s:%d",
            len(all_recipients),
            self._settings.smtp_host,
            self._settings.smtp_port,
        )

        # Bridge v3 port 1026: direkt SSL med self-signed cert
        async with aiosmtplib.SMTP(
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            use_tls=True,
            tls_context=self._ssl_ctx,
        ) as client:
            await client.login(self._settings.username, self._settings.password)
            await client.send_message(msg, recipients=all_recipients)

        logger.info("E-post skickad")
        return True

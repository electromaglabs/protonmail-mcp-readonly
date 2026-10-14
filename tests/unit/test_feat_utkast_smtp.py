"""Enhetstester för SMTPClient.send_prepared_message (feat-utkast)."""
import email
import email.policy
import pytest

from protonmail_mcp.smtp_client import SMTPPartialDeliveryError
from tests.fix_svar_support import capture_smtp, make_client


def _msg(headers: str, body: str = "Text"):
    raw = (headers.strip().replace("\n", "\r\n") + f"\r\n\r\n{body}\r\n").encode("utf-8")
    return email.message_from_bytes(raw, policy=email.policy.SMTP)


BASE = "From: me@proton.me\nSubject: Hej\nMessage-ID: <d1@proton.me>\n"


class TestSendPreparedMessage:
    @pytest.mark.asyncio
    async def test_recipients_from_to_cc_bcc_and_bcc_header_removed(self):
        msg = _msg(BASE + "To: Åsa <asa@example.se>, b@example.se\nCc: c@example.se\n"
                          "Bcc: h@example.se, \"Doe, J\" <j@example.se>")
        with capture_smtp() as cap:
            assert await make_client().send_prepared_message(msg) is True
        assert cap.recipients == ["asa@example.se", "b@example.se", "c@example.se",
                                  "h@example.se", "j@example.se"]
        assert cap.parsed["Bcc"] is None
        assert b"h@example.se" not in cap.raw
        # Originalet ändras inte (utkastet ska kunna behållas oförändrat)
        assert msg["Bcc"] is not None

    @pytest.mark.asyncio
    async def test_duplicate_recipients_are_sent_once(self):
        msg = _msg(BASE + "To: a@example.se\nCc: A@example.se\nBcc: a@example.se")
        with capture_smtp() as cap:
            await make_client().send_prepared_message(msg)
        assert cap.recipients == ["a@example.se"]

    @pytest.mark.asyncio
    async def test_encoded_display_names_cannot_add_recipients(self):
        # Ett kodat kommatecken eller <…> i namnet blir ingen ny mottagare
        msg = _msg(BASE + "To: =?utf-8?q?x=2C_<evil@attacker.example>?= <a@example.se>")
        with capture_smtp() as cap:
            await make_client().send_prepared_message(msg)
        assert cap.recipients == ["a@example.se"]

    @pytest.mark.asyncio
    async def test_idn_domain_is_punycoded_for_rcpt(self):
        msg = _msg(BASE + "To: user@exämple.se")
        with capture_smtp() as cap:
            await make_client().send_prepared_message(msg)
        assert cap.recipients == ["user@xn--exmple-cua.se"]

    @pytest.mark.asyncio
    async def test_without_recipients_nothing_is_sent(self):
        msg = _msg(BASE)
        with capture_smtp() as cap:
            with pytest.raises(ValueError, match="saknar mottagare"):
                await make_client().send_prepared_message(msg)
        assert cap.sent == []

    @pytest.mark.asyncio
    async def test_invalid_recipient_is_rejected(self):
        msg = _msg(BASE + "To: a@example.se, inte-en-adress@")
        with capture_smtp() as cap:
            with pytest.raises(ValueError, match="Ogiltig e-postadress"):
                await make_client().send_prepared_message(msg)
        assert cap.sent == []

    @pytest.mark.asyncio
    async def test_partial_delivery_raises(self):
        msg = _msg(BASE + "To: a@example.se\nCc: b@example.se")
        with capture_smtp() as cap:
            cap.refused["b@example.se"] = (550, "no such user")
            with pytest.raises(SMTPPartialDeliveryError) as excinfo:
                await make_client().send_prepared_message(msg)
        assert excinfo.value.delivered == ["a@example.se"]
        assert list(excinfo.value.refused) == ["b@example.se"]

    @pytest.mark.asyncio
    async def test_uses_tls_and_logs_in_like_send_email(self):
        import protonmail_mcp.smtp_client as mod

        msg = _msg(BASE + "To: a@example.se")
        client = make_client()
        with capture_smtp():
            await client.send_prepared_message(msg)
            kwargs = mod.aiosmtplib.SMTP.call_args.kwargs
            instance = mod.aiosmtplib.SMTP.return_value.__aenter__.return_value
        assert kwargs["use_tls"] is True
        assert kwargs["tls_context"] is client._ssl_ctx
        instance.login.assert_awaited_once_with("me@proton.me", "pw")

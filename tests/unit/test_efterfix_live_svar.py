"""L4: svar på ett mejl från det egna kontot till det egna kontot går till det egna kontot."""
import pytest

from protonmail_mcp.tools.reply import _parse_original, _reply_recipients

ME = "me@proton.me"


def _raw(from_, to, cc=None):
    lines = [f"From: {from_}", f"To: {to}"]
    if cc:
        lines.append(f"Cc: {cc}")
    lines += ["Subject: Test", "Message-ID: <a@x>", "", "Hej"]
    return "\r\n".join(lines).encode()


class TestReplyToSelf:
    def test_mail_to_self_replies_to_self(self):
        to, cc = _reply_recipients(_parse_original(_raw(ME, ME)), ME, False, [])
        assert to == [ME] and cc == []

    def test_display_name_and_case_are_kept(self):
        to, _ = _reply_recipients(_parse_original(_raw(f"Mattias <{ME.upper()}>", ME)), ME, False, [])
        assert to == [f"Mattias <{ME.upper()}>"]

    def test_reply_all_to_self_only(self):
        to, cc = _reply_recipients(_parse_original(_raw(ME, ME, cc=ME)), ME, True, [])
        assert to == [ME] and cc == []

    def test_own_sent_mail_to_others_still_goes_to_them(self):
        # Eget = bevisat skickat från kontot (efterfix-slut: inte bara From)
        to, _ = _reply_recipients(_parse_original(_raw(ME, "anna@x.se")), ME, False, [], sent_by_me=True)
        assert to == ["anna@x.se"]

    def test_unknown_own_address_still_errors(self):
        with pytest.raises(ValueError, match="Hittar ingen mottagare"):
            _reply_recipients(_parse_original(_raw("", "")), "", False, [])


class TestNeverGuessSelf:
    def test_unparseable_sender_to_self_is_still_an_error(self):
        raw = _raw("=?utf-8?q?Anna=0D=0ABcc=3A_evil@e.com?= <a@x.se>", ME)
        with pytest.raises(ValueError, match="Hittar ingen mottagare"):
            _reply_recipients(_parse_original(raw), ME, False, [])

    def test_other_sender_to_self_replies_to_sender(self):
        to, _ = _reply_recipients(_parse_original(_raw("anna@x.se", ME)), ME, False, [])
        assert to == ["anna@x.se"]

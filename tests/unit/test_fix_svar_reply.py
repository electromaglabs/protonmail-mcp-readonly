"""Enhetstester för fix-svar: reply_to_email och forward_email."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from protonmail_mcp.tools.reply import forward_email, reply_to_email
from tests.fix_svar_support import KONTO, capture_smtp, header_addresses, make_client


def _ctx(raw: bytes | None, account: str = KONTO):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()
    app.imap.get_message.return_value = raw
    app.smtp = make_client(account)
    return ctx


def _raw(headers: str, body: str = "Originaltext\r\n", content_type="text/plain; charset=utf-8") -> bytes:
    head = headers.strip().replace("\n", "\r\n")
    return (
        f"{head}\r\nContent-Type: {content_type}\r\n\r\n{body}"
    ).encode("utf-8")


# -------------------------------------------------------------------
# B8: ett enda Re:/Fwd:-prefix
# -------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("SV: möte", "Re: möte"),
        ("sv:möte", "Re: möte"),
        ("Re: Re: Re: möte", "Re: möte"),
        ("AW: WG: möte", "Re: WG: möte"),  # WG är inte i listan — lämnas orört
        ("Re [3] : möte", "Re: möte"),
        ("Svar: möte", "Re: Svar: möte"),  # "Svar" är inget prefix
        ("Vs. budget", "Re: Vs. budget"),
        ("  SV:   möte  ", "Re: möte"),
    ],
)
async def test_reply_subject_prefix_normalized(subject, expected):
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: {subject}\nMessage-ID: <m@x.se>")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert str(cap.parsed["Subject"]) == expected


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("möte", "Fwd: möte"),
        ("Fwd: Fwd: möte", "Fwd: möte"),
        ("VB: möte", "Fwd: möte"),
        ("SV: möte", "Fwd: möte"),
        ("Fw: Re: möte", "Fwd: möte"),
    ],
)
async def test_forward_subject_prefix_normalized(subject, expected):
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: {subject}\nMessage-ID: <m@x.se>")
    with capture_smtp() as cap:
        await forward_email(_ctx(raw), uid="1", to="b@x.se")
    assert str(cap.parsed["Subject"]) == expected


async def test_reply_subject_from_raw_utf8_header_is_not_mojibake():
    raw = (
        "From: Åsa Öberg <a@x.se>\r\nTo: me@proton.me\r\nSubject: SV: möte\r\n"
        "Message-ID: <m@x.se>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nx\r\n"
    ).encode("utf-8")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert str(cap.parsed["Subject"]) == "Re: möte"


async def test_reply_subject_with_encoded_linebreak_is_flattened():
    raw = _raw(
        "From: a@x.se\nTo: me@proton.me\nSubject: =?utf-8?q?m=C3=B6te=0D=0ABcc=3A_evil@e.com?=\n"
        "Message-ID: <m@x.se>"
    )
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert str(cap.parsed["Subject"]) == "Re: möte Bcc: evil@e.com"
    assert cap.parsed["Bcc"] is None
    assert cap.recipients == ["a@x.se"]


# -------------------------------------------------------------------
# B5: References läses skiftlägesokänsligt och bara som msg-id:n
# -------------------------------------------------------------------


@pytest.mark.parametrize("name", ["References", "references", "REFERENCES"])
async def test_references_any_case_is_chained(name):
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s\nMessage-ID: <m3@x>\n{name}: <m1@x>\n <m2@x>")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert str(cap.parsed["In-Reply-To"]) == "<m3@x>"
    assert " ".join(str(cap.parsed["References"]).split()) == "<m1@x> <m2@x> <m3@x>"


async def test_references_keeps_only_message_ids_and_dedupes():
    raw = _raw(
        f"From: a@x.se\nTo: {KONTO}\nSubject: s\nMessage-ID: <m3@x>\n"
        "References: =?utf-8?q?skr=C3=A4p?= <m1@x> junk <m1@x> <m3@x>"
    )
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert " ".join(str(cap.parsed["References"]).split()) == "<m1@x> <m3@x>"


async def test_in_reply_to_used_when_references_missing():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s\nMessage-ID: <m2@x>\nIn-Reply-To: <m1@x>")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert " ".join(str(cap.parsed["References"]).split()) == "<m1@x> <m2@x>"


async def test_no_message_id_means_no_threading_headers():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert cap.parsed["In-Reply-To"] is None
    assert cap.parsed["References"] is None


# -------------------------------------------------------------------
# Säkerhetsgranskning: originalets headers styrs av avsändaren och får
# inte kunna låsa servern (kvadratisk regex eller parsning)
# -------------------------------------------------------------------


def _elapsed(fn) -> float:
    import time

    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def test_prefix_stripping_is_linear_on_whitespace_runs():
    from protonmail_mcp.tools.reply import _base_subject

    assert _elapsed(lambda: _base_subject("re" + " " * 50_000 + "x")) < 0.2


def test_prefix_stripping_is_linear_on_many_prefixes():
    from protonmail_mcp.tools.reply import _base_subject

    assert _base_subject("re: " * 50_000 + "x") == "x"
    assert _elapsed(lambda: _base_subject("re: " * 50_000 + "x")) < 0.2


async def test_huge_references_header_is_cheap_and_trimmed():
    refs = " ".join(f"<r{i}@x.se>" for i in range(50_000))
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s\nMessage-ID: <m@x>\nReferences: {refs}")
    import time

    with capture_smtp() as cap:
        start = time.perf_counter()
        await reply_to_email(_ctx(raw), uid="1", body="ok")
        assert time.perf_counter() - start < 1.0
    ids = str(cap.parsed["References"]).split()
    # Första id:t (trådens rot) och de senaste behålls, och svarets id sist
    assert ids[0] == "<r0@x.se>" and ids[-1] == "<m@x>" and len(ids) <= 50


async def test_huge_subject_is_cheap():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: " + "möte " * 200_000 + "\nMessage-ID: <m@x>")
    import time

    with capture_smtp():
        start = time.perf_counter()
        try:
            await reply_to_email(_ctx(raw), uid="1", body="ok")
        except ValueError:
            pass  # ett orimligt ämne får avvisas, men snabbt
        assert time.perf_counter() - start < 1.0


# -------------------------------------------------------------------
# K3, B2, B3: mottagare, svara alla, citat, cc/bcc
# -------------------------------------------------------------------


def _to(cap):
    return header_addresses(cap.parsed, "To")


def _cc(cap):
    return header_addresses(cap.parsed, "Cc")


async def test_reply_to_header_wins_over_from():
    raw = _raw(f"From: n@x.se\nReply-To: Lista <l@x.se>\nTo: {KONTO}\nSubject: s\nMessage-ID: <m@x>")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert _to(cap) == [("Lista", "l@x.se")]
    assert cap.recipients == ["l@x.se"]


async def test_reply_header_case_insensitive_reply_to():
    raw = _raw(f"From: n@x.se\nreply-to: l@x.se\nTo: {KONTO}\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert cap.recipients == ["l@x.se"]


async def test_reply_without_reply_all_ignores_other_recipients():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}, b@x.se\nCc: c@x.se\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert cap.recipients == ["a@x.se"]
    assert cap.parsed["Cc"] is None


async def test_reply_all_dedupes_and_drops_own_account_case_insensitively():
    raw = _raw(
        "From: Anna <a@x.se>\n"
        f"To: {KONTO.upper()}, Bo <b@x.se>, a@x.se\n"
        "Cc: B@X.SE, c@x.se, Me <me@PROTON.me>\n"
        "Subject: s"
    )
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok", reply_all=True)
    assert _to(cap) == [("Anna", "a@x.se"), ("Bo", "b@x.se")]
    assert _cc(cap) == [("", "c@x.se")]
    assert cap.recipients == ["a@x.se", "b@x.se", "c@x.se"]


async def test_reply_all_with_reply_to_uses_reply_to_instead_of_from():
    raw = _raw(f"From: n@x.se\nReply-To: l@x.se\nTo: {KONTO}, b@x.se\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok", reply_all=True)
    assert [a for _, a in _to(cap)] == ["l@x.se", "b@x.se"]


@pytest.mark.parametrize(
    "from_header, expected",
    [
        ("=?utf-8?q?Svensson=2C_=C3=85sa?= <asa@x.se>", [("Svensson, Åsa", "asa@x.se")]),
        ('"Doe, John" <j@x.com>', [("Doe, John", "j@x.com")]),
        ("a@x.se, b@y.se", [("", "a@x.se"), ("", "b@y.se")]),
        ("=?utf-8?q?boss=40company=2Ecom?= <attacker@evil.com>", [("boss@company.com", "attacker@evil.com")]),
        # email.policy tolkar inte kommentaren som namn; adressen är det viktiga
        ("a@x.se (Anna Andersson)", [("", "a@x.se")]),
    ],
)
async def test_reply_reads_addresses_from_raw_header(from_header, expected):
    raw = _raw(f"From: {from_header}\nTo: {KONTO}\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert _to(cap) == expected
    assert cap.recipients == [a for _, a in expected]


async def test_reply_from_raw_utf8_header_keeps_name():
    raw = (
        "From: Åsa Öberg <a@x.se>\r\nTo: me@proton.me\r\nSubject: s\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\nx\r\n"
    ).encode("utf-8")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert _to(cap) == [("Åsa Öberg", "a@x.se")]


async def test_encoded_linebreak_in_display_name_is_flattened():
    raw = _raw(f"From: =?utf-8?q?Anna=0D=0ABcc=3A_evil@e.com?= <a@x.se>\nTo: {KONTO}\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert cap.recipients == ["a@x.se"]
    assert cap.parsed["Bcc"] is None


async def test_reply_to_own_sent_message_goes_to_original_recipients():
    raw = _raw(f"From: Me <{KONTO}>\nTo: Bo <b@x.se>\nCc: c@x.se\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok", mailbox="Sent")
    assert _to(cap) == [("Bo", "b@x.se")]
    assert cap.recipients == ["b@x.se"]


async def test_reply_all_to_own_sent_message_includes_cc():
    raw = _raw(f"From: {KONTO}\nTo: b@x.se\nCc: c@x.se, {KONTO}\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok", reply_all=True)
    assert [a for _, a in _to(cap)] == ["b@x.se"]
    assert [a for _, a in _cc(cap)] == ["c@x.se"]


async def test_reply_to_note_to_self_without_other_recipients_is_an_error():
    raw = _raw(f"From: {KONTO}\nTo: {KONTO}\nSubject: s")
    with capture_smtp() as cap:
        with pytest.raises(ValueError, match="mottagare"):
            await reply_to_email(_ctx(raw), uid="1", body="ok")
    assert cap.sent == []


async def test_reply_with_extra_cc_and_bcc():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(
            _ctx(raw), uid="1", body="ok", cc=["c@x.se"], bcc="h@x.se"
        )
    assert [a for _, a in _cc(cap)] == ["c@x.se"]
    assert cap.recipients == ["a@x.se", "c@x.se", "h@x.se"]
    assert cap.parsed["Bcc"] is None


async def test_reply_all_with_extra_cc_does_not_duplicate():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nCc: c@x.se\nSubject: s")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok", reply_all=True, cc="C@x.se")
    assert cap.recipients == ["a@x.se", "c@x.se"]


async def test_reply_quotes_original_plain_text():
    raw = _raw(
        f"From: Anna Ek <a@x.se>\nTo: {KONTO}\nSubject: s\nDate: Mon, 12 Oct 2026 09:30:00 +0200",
        body="Hej!\r\n\r\n> tidigare\r\nSes!\r\n",
    )
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="Tack")
    text = cap.parsed.get_body(("plain",)).get_content().replace("\r\n", "\n")
    assert text == (
        "Tack\n\nDen 2026-10-12 09:30 skrev Anna Ek:\n> Hej!\n>\n> > tidigare\n> Ses!\n"
    )


async def test_reply_quote_without_date_or_name():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s", body="Hej\r\n")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="Tack")
    text = cap.parsed.get_body(("plain",)).get_content()
    assert "a@x.se skrev:\n> Hej" in text.replace("\r\n", "\n")


async def test_reply_quote_of_html_only_original_uses_text():
    raw = _raw(
        f"From: a@x.se\nTo: {KONTO}\nSubject: s",
        body="<html><body><p>Viktigt innehåll</p></body></html>\r\n",
        content_type="text/html; charset=utf-8",
    )
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="Tack")
    text = cap.parsed.get_body(("plain",)).get_content()
    assert "> Viktigt innehåll" in text


async def test_reply_can_skip_quote():
    raw = _raw(f"From: a@x.se\nTo: {KONTO}\nSubject: s", body="Hemligt\r\n")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="Tack", quote_original=False)
    text = cap.parsed.get_body(("plain",)).get_content()
    assert text.strip() == "Tack"


async def test_reply_html_body_gets_escaped_blockquote():
    raw = _raw(f"From: Anna <a@x.se>\nTo: {KONTO}\nSubject: s", body="1 < 2 & <b>fet</b>\r\n")
    with capture_smtp() as cap:
        await reply_to_email(
            _ctx(raw), uid="1", body="Tack", body_html="<html><body><p>Tack</p></body></html>"
        )
    html = cap.parsed.get_body(("html",)).get_content()
    assert "<blockquote" in html
    assert "1 &lt; 2 &amp; &lt;b&gt;fet&lt;/b&gt;" in html
    # Citatet hamnar inne i body, inte efter </html>
    assert html.index("<blockquote") < html.lower().index("</body>")


async def test_reply_with_mocked_smtp_still_works_without_account_address():
    """Befintliga verktygstester använder en AsyncMock som SMTP-klient."""
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()
    app.imap.get_message.return_value = _raw("From: a@x.se\nTo: b@x.se\nSubject: s")
    app.smtp = AsyncMock()
    app.smtp.send_email.return_value = True
    assert await reply_to_email(ctx, uid="1", body="ok") is True
    kwargs = app.smtp.send_email.call_args.kwargs
    assert kwargs["to"] == ["a@x.se"]


def test_smtp_client_exposes_account_address():
    assert make_client("Me@Proton.me").account_address == "Me@Proton.me"


async def test_non_ascii_message_id_is_skipped_instead_of_crashing():
    raw = (
        "From: a@x.se\r\nTo: me@proton.me\r\nSubject: s\r\nMessage-ID: <ö@x>\r\n"
        "References: <r1@x> <å@x>\r\n\r\nhej\r\n"
    ).encode("utf-8")
    with capture_smtp() as cap:
        await reply_to_email(_ctx(raw), uid="1", body="ok")
        cap.raw  # serialiseringen får inte krascha
    assert cap.parsed["In-Reply-To"] is None
    assert cap.parsed["References"] is None


# -------------------------------------------------------------------
# K4, B4: vidarebefordran med bilagor, HTML och cc/bcc
# -------------------------------------------------------------------


def _orig_msg(subject="s"):
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = "Anna <a@x.se>"
    msg["To"] = KONTO
    msg["Subject"] = subject
    msg["Message-ID"] = "<m@x>"
    return msg


async def test_forward_html_only_includes_html_and_text_version():
    msg = _orig_msg()
    msg.set_content("<html><body><p>Viktigt <b>innehåll</b></p></body></html>", subtype="html")
    with capture_smtp() as cap:
        await forward_email(_ctx(msg.as_bytes()), uid="1", to="b@x.se", body="FYI")
    sent = cap.parsed
    plain = sent.get_body(("plain",)).get_content()
    html = sent.get_body(("html",)).get_content()
    assert "FYI" in plain and "Viktigt innehåll" in plain
    assert "<p>Viktigt <b>innehåll</b></p>" in html
    # Användarens text och rubrikblocket hamnar inne i originalets <body>
    assert html.index("FYI") > html.lower().index("<body")
    assert "Forwarded message" in html


async def test_forward_user_text_is_escaped_in_html():
    msg = _orig_msg()
    msg.set_content("<p>x</p>", subtype="html")
    with capture_smtp() as cap:
        await forward_email(_ctx(msg.as_bytes()), uid="1", to="b@x.se", body="<script>1</script>")
    html = cap.parsed.get_body(("html",)).get_content()
    assert "<script>" not in html and "&lt;script&gt;" in html


async def test_forward_plain_only_original_has_no_html_part():
    msg = _orig_msg()
    msg.set_content("Bara text")
    with capture_smtp() as cap:
        await forward_email(_ctx(msg.as_bytes()), uid="1", to="b@x.se")
    assert cap.parsed.get_body(("html",)) is None
    assert "Bara text" in cap.parsed.get_body(("plain",)).get_content()


async def test_forward_keeps_all_attachments_byte_for_byte():
    msg = _orig_msg()
    msg.set_content("Se bilagor")
    msg.add_alternative("<p>Se bilagor</p>", subtype="html")
    msg.add_attachment(b"\x00\x01binar", maintype="application", subtype="octet-stream", filename="data.bin")
    msg.add_attachment("rad 1\nrad 2\n", filename="anteckning.txt")
    with capture_smtp() as cap:
        await forward_email(_ctx(msg.as_bytes()), uid="1", to="b@x.se")
    found = {a.get_filename(): a for a in cap.parsed.iter_attachments()}
    assert found["data.bin"].get_content() == b"\x00\x01binar"
    assert found["anteckning.txt"].get_content().replace("\r\n", "\n") == "rad 1\nrad 2\n"
    assert cap.parsed.get_body(("html",)) is not None


async def test_forward_keeps_attached_message():
    inner = _orig_msg("Inre mejl")
    inner.set_content("inre text")
    msg = _orig_msg()
    msg.set_content("Se bifogat mejl")
    msg.add_attachment(inner)
    with capture_smtp() as cap:
        await forward_email(_ctx(msg.as_bytes()), uid="1", to="b@x.se")
    attached = [a for a in cap.parsed.iter_attachments() if a.get_content_type() == "message/rfc822"]
    assert len(attached) == 1
    assert str(attached[0].get_content()["Subject"]) == "Inre mejl"
    # Det bifogade mejlets text ska inte bli brödtext i vidarebefordran
    assert "inre text" not in cap.parsed.get_body(("plain",)).get_content()


async def test_forward_keeps_inline_image_related_to_html():
    msg = _orig_msg()
    msg.set_content("text")
    msg.add_alternative('<p><img src="cid:logo@x"></p>', subtype="html")
    msg.get_body(("html",)).add_related(
        b"\x89PNGfejk", maintype="image", subtype="png", cid="<logo@x>"
    )
    with capture_smtp() as cap:
        await forward_email(_ctx(msg.as_bytes()), uid="1", to="b@x.se")
    sent = cap.parsed
    html_part = sent.get_body(("html",))
    assert 'src="cid:logo@x"' in html_part.get_content()
    images = [p for p in sent.walk() if p.get_content_type() == "image/png"]
    assert len(images) == 1 and images[0]["Content-ID"] == "<logo@x>"
    assert images[0].get_content() == b"\x89PNGfejk"
    # Bilden ska ligga i samma multipart/related som HTML-delen
    related = [p for p in sent.walk() if p.get_content_type() == "multipart/related"]
    assert related and any(p is images[0] for p in related[0].iter_parts())


async def test_forward_with_cc_and_bcc():
    msg = _orig_msg()
    msg.set_content("x")
    with capture_smtp() as cap:
        await forward_email(
            _ctx(msg.as_bytes()), uid="1", to=["b@x.se"], cc="c@x.se", bcc=["h@x.se"]
        )
    assert [a for _, a in _cc(cap)] == ["c@x.se"]
    assert cap.recipients == ["b@x.se", "c@x.se", "h@x.se"]
    assert cap.parsed["Bcc"] is None


async def test_forward_header_block_is_decoded():
    raw = (
        "From: =?utf-8?q?Svensson=2C_=C3=85sa?= <asa@x.se>\r\nTo: me@proton.me\r\n"
        "Subject: SV: möte\r\nDate: Mon, 12 Oct 2026 09:30:00 +0200\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\nhej\r\n"
    ).encode("utf-8")
    with capture_smtp() as cap:
        await forward_email(_ctx(raw), uid="1", to="b@x.se")
    plain = cap.parsed.get_body(("plain",)).get_content()
    assert 'From: "Svensson, Åsa" <asa@x.se>' in plain
    assert "Subject: SV: möte" in plain
    assert "To: me@proton.me" in plain


async def test_forward_with_mocked_smtp_passes_attachments_keyword():
    """Befintliga verktygstester använder en AsyncMock som SMTP-klient."""
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()
    app.imap.get_message.return_value = _raw("From: a@x.se\nTo: b@x.se\nSubject: s")
    app.smtp = AsyncMock()
    app.smtp.send_email.return_value = True
    assert await forward_email(ctx, uid="1", to="c@x.se") is True



@pytest.mark.parametrize(
    "markup, expected",
    [
        ("<p>Hej</p><p>Ses &amp; hörs</p>", "Hej\nSes & hörs"),
        ("rad 1<br>rad 2<br/>rad 3", "rad 1\nrad 2\nrad 3"),
        ("<style>p{color:red}</style><script>alert(1)</script><div>Text</div>", "Text"),
        ("<html><head><title>T</title></head><body>  A  </body></html>", "T\nA"),
        ("1 < 2 och 3 > 2", "1 < 2 och 3 > 2"),
    ],
)
def test_html_to_text(markup, expected):
    from protonmail_mcp.tools.reply import _html_to_text

    assert _html_to_text(markup) == expected

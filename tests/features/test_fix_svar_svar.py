"""BDD-steg för fix_svar_svar.feature och fix_svar_vidarebefordra.feature.

Verktygen körs mot den riktiga SMTPClient; bara IMAP-hämtningen och
aiosmtplib är attrapper, så stegen granskar det som skulle gått ut på tråden.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from email.message import EmailMessage

from protonmail_mcp.tools.reply import forward_email, reply_to_email
from tests.fix_svar_support import capture_smtp, header_addresses, make_client

scenarios("fix_svar_svar.feature", "fix_svar_vidarebefordra.feature")

PDF_BYTES = b"%PDF-1.4 fejkad faktura \x00\x01\x02"


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@pytest.fixture
def captured():
    with capture_smtp() as c:
        yield c


@pytest.fixture
def mailbox():
    """(mapp, uid) -> rått meddelande."""
    return {}


@pytest.fixture
def outcome():
    return {}


@given(parsers.parse('mitt konto är "{account}"'), target_fixture="ctx")
def account_ctx(account, mailbox):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()

    async def get_message(folder, uid):
        return mailbox.get((folder, uid))

    app.imap.get_message.side_effect = get_message
    app.smtp = make_client(account)
    return ctx


@given(parsers.parse('ett mejl med UID "{uid}" från "{sender}" med ämnet "{subject}"'))
def simple_message(mailbox, uid, sender, subject):
    mailbox[("INBOX", uid)] = (
        f"From: {sender}\r\n"
        "To: me@proton.me\r\n"
        f"Subject: {subject}\r\n"
        "Date: Mon, 12 Oct 2026 09:30:00 +0200\r\n"
        f"Message-ID: <orig-{uid}@example.se>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Originaltext\r\n"
    ).encode("utf-8")


def _store(mailbox, folder, uid, docstring):
    """Lägg ett meddelande i attrappens brevlåda. Docstringen är headers,
    eventuellt följda av en tom rad och brödtexten."""
    head, _, body = docstring.strip().partition("\n\n")
    head = "\r\n".join(line.strip() for line in head.splitlines())
    body = "\r\n".join(body.splitlines()) if body else "Originaltext"
    mailbox[(folder, uid)] = (
        f"{head}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n"
    ).encode("utf-8")


@given(parsers.re(r'ett mejl med UID "(?P<uid>[^"]+)" med följande (?:headers|innehåll):'))
def message_with_headers(mailbox, uid, docstring):
    _store(mailbox, "INBOX", uid, docstring)


@given(parsers.parse('ett mejl med UID "{uid}" i mappen "{folder}" med följande headers:'))
def message_in_folder(mailbox, uid, folder, docstring):
    _store(mailbox, folder, uid, docstring)


def _run(outcome, coro):
    try:
        outcome["result"] = asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001 — scenariot granskar felet
        outcome["error"] = exc


@when(parsers.re(r'jag svarar på mejlet med UID "(?P<uid>[^"]+)" med texten "(?P<text>[^"]*)"'))
def reply(ctx, captured, outcome, uid, text):
    _run(outcome, reply_to_email(ctx, uid=uid, body=text))


@when(parsers.re(r'jag svarar alla på mejlet med UID "(?P<uid>[^"]+)" med texten "(?P<text>[^"]*)"'))
def reply_all(ctx, captured, outcome, uid, text):
    _run(outcome, reply_to_email(ctx, uid=uid, body=text, reply_all=True))


@when(
    parsers.re(
        r'jag svarar(?P<all> alla)? på mejlet med UID "(?P<uid>[^"]+)" i mappen '
        r'"(?P<folder>[^"]+)" med texten "(?P<text>[^"]*)"'
    )
)
def reply_in_folder(ctx, captured, outcome, all, uid, folder, text):
    _run(
        outcome,
        reply_to_email(ctx, uid=uid, body=text, mailbox=folder, reply_all=bool(all)),
    )


@when(
    parsers.parse(
        'jag svarar på mejlet med UID "{uid}" med kopia till "{cc}" och hemlig kopia till "{bcc}"'
    )
)
def reply_with_cc_bcc(ctx, captured, outcome, uid, cc, bcc):
    _run(outcome, reply_to_email(ctx, uid=uid, body="Se kopia", cc=cc, bcc=bcc))


def _sent(captured, outcome):
    assert "error" not in outcome, outcome.get("error")
    return captured.parsed


@then(parsers.parse('ska svaret gå till "{addrs}"'))
def reply_goes_to(captured, outcome, addrs):
    assert [a for _, a in header_addresses(_sent(captured, outcome), "To")] == _split(addrs)


@then(parsers.parse('ska svaret ha kopia till "{addrs}"'))
def reply_cc(captured, outcome, addrs):
    assert [a for _, a in header_addresses(_sent(captured, outcome), "Cc")] == _split(addrs)


@then("ska svaret inte ha någon kopia")
def reply_no_cc(captured, outcome):
    assert _sent(captured, outcome)["Cc"] is None


@then(parsers.parse('ska svaret sakna headern "{name}"'))
def reply_lacks_header(captured, outcome, name):
    assert name not in _sent(captured, outcome)


@then(parsers.parse('ska mottagaren "{addr}" heta "{name}" i svaret'))
def reply_recipient_name(captured, outcome, addr, name):
    assert (name, addr) in header_addresses(_sent(captured, outcome), "To")


@then(parsers.parse('SMTP-mottagarna ska vara "{addrs}"'))
def reply_rcpt(captured, outcome, addrs):
    _sent(captured, outcome)
    assert captured.recipients == _split(addrs)


def _plain_body(captured, outcome) -> str:
    return _sent(captured, outcome).get_body(("plain",)).get_content()


@then(parsers.parse('ska svarets brödtext börja med "{text}"'))
def body_starts(captured, outcome, text):
    assert _plain_body(captured, outcome).startswith(text)


@then(parsers.parse('ska svarets brödtext innehålla "{text}"'))
def body_contains(captured, outcome, text):
    assert text in _plain_body(captured, outcome)


@then(parsers.parse('ska svarets ämne vara "{subject}"'))
def reply_subject(captured, outcome, subject):
    assert "error" not in outcome, outcome.get("error")
    assert str(captured.parsed["Subject"]) == subject


@then(parsers.re(r'ska svarets (?P<header>[A-Z][A-Za-z-]+) vara "(?P<value>[^"]*)"'))
def reply_header(captured, outcome, header, value):
    assert "error" not in outcome, outcome.get("error")
    assert " ".join(str(captured.parsed[header]).split()) == value


# --- Vidarebefordran ---------------------------------------------------


def _original(uid: str, subject: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "Anna <anna@example.se>"
    msg["To"] = "me@proton.me"
    msg["Subject"] = subject
    msg["Date"] = "Mon, 12 Oct 2026 09:30:00 +0200"
    msg["Message-ID"] = f"<orig-{uid}@example.se>"
    return msg


@given(parsers.parse('ett nyhetsbrev med UID "{uid}" som bara har HTML-innehållet "{html}"'))
def html_only_message(mailbox, uid, html):
    msg = _original(uid, "Nyhetsbrev")
    msg.set_content(f"<html><body>{html}</body></html>", subtype="html")
    mailbox[("INBOX", uid)] = msg.as_bytes()


@given(parsers.parse('ett mejl med UID "{uid}" med bilagan "{filename}" av typen "{ctype}"'))
def message_with_attachment(mailbox, uid, filename, ctype):
    msg = _original(uid, "Faktura")
    msg.set_content("Fakturan bifogas.")
    maintype, subtype = ctype.split("/")
    msg.add_attachment(PDF_BYTES, maintype=maintype, subtype=subtype, filename=filename)
    mailbox[("INBOX", uid)] = msg.as_bytes()


@when(
    parsers.re(
        r'jag vidarebefordrar mejlet med UID "(?P<uid>[^"]+)" till "(?P<to>[^"]+)" '
        r'med texten "(?P<text>[^"]*)"'
    )
)
def forward(ctx, captured, outcome, uid, to, text):
    _run(outcome, forward_email(ctx, uid=uid, to=to, body=text))


@when(
    parsers.parse(
        'jag vidarebefordrar mejlet med UID "{uid}" till "{to}" med kopia till "{cc}" '
        'och hemlig kopia till "{bcc}"'
    )
)
def forward_cc_bcc(ctx, captured, outcome, uid, to, cc, bcc):
    _run(outcome, forward_email(ctx, uid=uid, to=to, cc=cc, bcc=bcc))


@then(parsers.parse('ska den vidarebefordrade texten innehålla "{text}"'))
def forwarded_text(captured, outcome, text):
    assert text in _plain_body(captured, outcome)


@then(parsers.parse('ska den vidarebefordrade HTML-versionen innehålla "{text}"'))
def forwarded_html(captured, outcome, text):
    html_part = _sent(captured, outcome).get_body(("html",))
    assert html_part is not None, "ingen HTML-del"
    assert text in html_part.get_content()


@then(
    parsers.parse(
        'ska det vidarebefordrade mejlet ha bilagan "{filename}" av typen "{ctype}" med samma innehåll'
    )
)
def forwarded_attachment(captured, outcome, filename, ctype):
    attachments = list(_sent(captured, outcome).iter_attachments())
    found = [(a.get_filename(), a.get_content_type(), a.get_content()) for a in attachments]
    assert (filename, ctype, PDF_BYTES) in found

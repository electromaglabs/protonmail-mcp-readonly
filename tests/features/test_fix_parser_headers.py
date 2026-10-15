"""BDD-tester för avkodning av rubriker (fix-parser)."""
import asyncio

from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.imap_client import _parse_fetch_metadata
from protonmail_mcp.tools.messages import get_email

scenarios("fix_parser_headers.feature")


@given(parsers.parse('ett mejl med rubrikraden "{line}"'), target_fixture="raw")
def mail_with_header(mock_ctx, line):
    raw = f"From: a@b.se\r\n{line}\r\n\r\nbody\r\n".encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@when("jag hämtar mejlet med get_email", target_fixture="result")
def fetch_mail(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX"))


@then(parsers.parse('ska ämnet vara "{subject}"'))
def subject_is(result, subject):
    assert result["subject"] == subject


@given(
    parsers.parse('en IMAP-sida med tre mejl där det mittersta har ämnet "{subject}"'),
    target_fixture="fetch_lines",
)
def imap_page(subject):
    lines = []
    for uid, subj in [(1, "ok"), (2, subject), (3, "ok")]:
        lines.append(f"* {uid} FETCH (UID {uid} FLAGS () BODY[HEADER] {{10}}".encode())
        lines.append(bytearray(f"Subject: {subj}\r\n\r\n".encode()))
    return lines


@when("sidans metadata parsas", target_fixture="listing")
def parse_page(fetch_lines):
    return _parse_fetch_metadata(fetch_lines)


@then(parsers.parse("ska {count:d} mejl listas"))
def listed_count(listing, count):
    assert len(listing) == count


@then(parsers.parse('det mittersta mejlets ämne ska vara "{subject}"'))
def middle_subject(listing, subject):
    assert listing[1]["subject"] == subject


@given(
    parsers.parse('ett mejl med råa UTF-8-rubriker från "{sender}" med ämnet "{subject}"'),
    target_fixture="raw",
)
def mail_with_raw_utf8(mock_ctx, sender, subject):
    raw = (
        f"From: {sender}\r\nTo: Örjan <o@x.se>\r\nSubject: {subject}\r\n"
        "Date: Mån, 1 Jan 2024 10:00:00 +0100\r\nMessage-ID: <å@x.se>\r\n"
        "Sender: Göran <g@x.se>\r\n\r\nhej\r\n"
    ).encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@then(parsers.parse('avsändaren ska vara "{sender}"'))
def sender_is(result, sender):
    assert result["from"] == sender


@then("alla fält ska gå att serialisera som JSON")
def json_serializable(result):
    import json

    json.dumps(result, ensure_ascii=False).encode("utf-8")


@then(parsers.parse('ska mottagarna vara "{first}" och "{second}"'))
def recipients_are(result, first, second):
    assert result["to"] == [first, second]


@given(parsers.parse('ett mejl från "{sender}" i INBOX'), target_fixture="raw")
def mail_from(mock_ctx, sender):
    raw = f"From: {sender}\r\nSubject: Fråga\r\nMessage-ID: <q@x.se>\r\n\r\nhej\r\n".encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@when("jag svarar på mejlet med reply_to_email", target_fixture="sent_to")
def reply(mock_ctx, raw):
    from protonmail_mcp.tools.reply import reply_to_email

    smtp = mock_ctx.request_context.lifespan_context.smtp
    smtp.send_email.return_value = True
    asyncio.run(reply_to_email(mock_ctx, mailbox="INBOX", uid="1", body="Svar"))
    return smtp.send_email.call_args.kwargs["to"]


@then(parsers.parse('ska svaret skickas till adressen "{addr}"'))
def reply_goes_to(sent_to, addr):
    from email.utils import parseaddr

    assert parseaddr(sent_to)[1] == addr


@then("mottagaren ska godkännas av SMTP-klientens adresskontroll")
def smtp_accepts(sent_to):
    from protonmail_mcp.smtp_client import _validate_email_addr

    _validate_email_addr(sent_to)


@given(
    parsers.parse('ett mejl med Message-ID "{msgid}" och rubriken "{header}" i INBOX'),
    target_fixture="raw",
)
def mail_with_refs(mock_ctx, msgid, header):
    raw = f"From: a@b.se\r\nSubject: s\r\nMessage-ID: {msgid}\r\n{header}\r\n\r\nhej\r\n".encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@then(parsers.parse('ska svarets References vara "{refs}"'))
def reply_references(mock_ctx, sent_to, refs):
    kwargs = mock_ctx.request_context.lifespan_context.smtp.send_email.call_args.kwargs
    assert kwargs["additional_headers"]["References"] == refs

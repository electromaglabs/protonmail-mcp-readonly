"""BDD-steg för feat_bilagor_skicka.feature (attachments på send/reply/forward).

Verktygen körs mot den riktiga SMTPClient; IMAP och aiosmtplib är attrapper,
så stegen granskar det som skulle ha gått ut på tråden. Inget mejl skickas.
"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.reply import forward_email, reply_to_email
from protonmail_mcp.tools.send import send_email
from tests.feat_bilagor_support import (  # noqa: F401
    attachment_env,
    base64_part,
    multipart,
    raw_message,
    text_part,
)
from tests.fix_svar_support import capture_smtp, make_client

scenarios("feat_bilagor_skicka.feature")

PDF = b"%PDF-1.4 offert \x00\xff"


@pytest.fixture
def captured():
    with capture_smtp() as c:
        yield c


@pytest.fixture
def state():
    return {"mailbox": {}}


@pytest.fixture
def root(attachment_env):
    attachment_env[0].mkdir(mode=0o700)
    return attachment_env[0]


@given(
    parsers.parse('mitt konto är "{account}" och bilagekatalogen innehåller "{name}"'),
    target_fixture="ctx",
)
def account(root, state, account, name):
    (root / name).write_bytes(PDF)
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()

    async def get_message(folder, uid):
        return state["mailbox"].get((folder, uid))

    app.imap.get_message.side_effect = get_message
    app.smtp = make_client(account)
    return ctx


@given(parsers.parse('att bilagekatalogen också innehåller "{name}"'))
def another_file(root, name):
    (root / name).write_bytes(PDF)


@given(parsers.parse(
    'att bilagekatalogen också innehåller "{first}" och "{second}" på {mb:d} MB vardera'
))
def big_files(root, first, second, mb):
    for name in (first, second):
        with open(root / name, "wb") as fh:
            fh.truncate(mb * 1024 * 1024)  # gles fil, tar ingen plats


@given(parsers.parse('en fil "{name}" utanför bilagekatalogen'))
def outside_file(attachment_env, name):
    (attachment_env[1] / name).write_text("hemligt")


@given(parsers.parse('ett mejl med UID "{uid}" i "{folder}" från "{sender}"'))
def original(state, uid, folder, sender):
    state["mailbox"][(folder, uid)] = (
        f"From: {sender}\r\nTo: me@proton.me\r\nSubject: Fråga\r\n"
        f"Message-ID: <orig-{uid}@example.se>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\nHej!\r\n"
    ).encode("utf-8")


@given(parsers.parse('ett mejl med UID "{uid}" i "{folder}" från "{sender}" med bilagan "{name}"'))
def original_with_attachment(state, uid, folder, sender, name):
    state["mailbox"][(folder, uid)] = raw_message(
        multipart(text_part(), base64_part("application/pdf", f'; filename="{name}"', b"%PDF faktura"))
    ).replace(b"anna@example.se", sender.encode())


def _run(state, coro):
    try:
        state["result"] = asyncio.run(coro)
    except ValueError as exc:
        state["error"] = exc


@when(parsers.re(r'jag skickar ett mejl till "(?P<to>[^"]+)" med bilagan "(?P<name>[^"]+)"$'))
def send_one(ctx, captured, state, to, name):
    _run(state, send_email(ctx, to=to, subject="Offert", body="Se bilagan.", attachments=[name]))


@when(parsers.parse('jag skickar ett mejl med HTML till "{to}" med bilagan "{name}"'))
def send_html(ctx, captured, state, to, name):
    _run(state, send_email(
        ctx, to=to, subject="Offert", body="Se bilagan.", body_html="<p>Se bilagan.</p>",
        attachments=[name],
    ))


@when(parsers.parse('jag skickar ett mejl till "{to}" med bilagan "{name}" {count:d} gånger'))
def send_many(ctx, captured, state, to, name, count):
    _run(state, send_email(ctx, to=to, subject="x", body="x", attachments=[name] * count))


@when(parsers.parse('jag skickar ett mejl till "{to}" med bilagorna "{first}" och "{second}"'))
def send_two(ctx, captured, state, to, first, second):
    _run(state, send_email(ctx, to=to, subject="x", body="x", attachments=[first, second]))


@when(parsers.parse('jag svarar på mejlet "{uid}" i "{folder}" med bilagan "{name}"'))
def reply(ctx, captured, state, uid, folder, name):
    _run(state, reply_to_email(ctx, uid=uid, body="Svar", mailbox=folder, attachments=[name]))


@when(parsers.parse(
    'jag vidarebefordrar mejlet "{uid}" i "{folder}" till "{to}" med bilagan "{name}"'
))
def forward(ctx, captured, state, uid, folder, to, name):
    _run(state, forward_email(ctx, uid=uid, to=to, mailbox=folder, attachments=[name]))


def _attachments(captured):
    return [p for p in captured.parsed.iter_attachments()]


@then(parsers.parse('ska mejlet vara "{ctype}"'))
def message_type(captured, ctype):
    assert captured.parsed.get_content_type() == ctype


@then("ska första delen vara texten")
def first_is_text(captured):
    first = next(captured.parsed.iter_parts())
    assert first.get_content_type() == "text/plain"
    assert first.get_content().strip() == "Se bilagan."


@then(parsers.parse('ska första delen vara "{ctype}" med text och HTML'))
def first_is_alternative(captured, ctype):
    first = next(captured.parsed.iter_parts())
    assert first.get_content_type() == ctype
    assert [p.get_content_type() for p in first.iter_parts()] == ["text/plain", "text/html"]


@then(parsers.parse(
    'ska mejlet ha bilagan "{name}" av typen "{ctype}" med filens innehåll'
))
def has_attachment_with_content(captured, name, ctype):
    matches = [p for p in _attachments(captured) if p.get_filename() == name]
    assert len(matches) == 1, [p.get_filename() for p in _attachments(captured)]
    assert matches[0].get_content_type() == ctype
    assert matches[0].get_content_disposition() == "attachment"
    assert matches[0].get_payload(decode=True) == PDF


@then(parsers.parse('ska mejlet ha bilagan "{name}" av typen "{ctype}"'))
def has_attachment(captured, name, ctype):
    assert any(
        p.get_filename() == name and p.get_content_type() == ctype for p in _attachments(captured)
    )


@then(parsers.parse('ska Content-Disposition för bilagan innehålla "{text}"'))
def disposition_raw(captured, text):
    raw = captured.raw.decode("ascii")
    unfolded = raw.replace("\r\n ", " ")
    assert text in unfolded


@then(parsers.parse('ska sändningen avvisas med ett fel som nämner "{text}"'))
def rejected(state, text):
    assert "result" not in state
    assert text in str(state["error"])


@then("inget mejl ska ha skickats")
def nothing_sent(captured):
    assert captured.sent == []


@then(parsers.parse('ska svaret gå till "{addr}" med In-Reply-To satt'))
def reply_headers(captured, addr):
    assert captured.recipients == [addr]
    assert captured.parsed["In-Reply-To"] == "<orig-5@example.se>"

"""BDD-steg för utkastflödet (feat_utkast_*.feature).

Verktygen körs mot den riktiga IMAPClient och SMTPClient; bara aioimaplib
(låtsas-Bridge med riktiga meddelanden) och aiosmtplib är attrapper, så
stegen granskar både det som hamnar i Drafts och det som går ut på tråden.
"""
import asyncio
from email.message import EmailMessage
from unittest.mock import MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.drafts import (
    create_draft,
    create_forward_draft,
    create_reply_draft,
    send_draft,
    update_draft,
)
from protonmail_mcp.tools.reply import reply_to_email
from tests.feat_utkast_bridge import make_imap
from tests.fix_svar_support import capture_smtp, header_addresses, make_client

scenarios(
    "feat_utkast_skapa.feature",
    "feat_utkast_svar.feature",
    "feat_utkast_uppdatera.feature",
    "feat_utkast_skicka.feature",
)


@pytest.fixture
def captured():
    with capture_smtp() as c:
        yield c


@pytest.fixture
def outcome():
    return {}


@pytest.fixture
def bridge_pair():
    return make_imap()


@pytest.fixture
def bridge(bridge_pair):
    return bridge_pair[1]


def _run(outcome, coro):
    try:
        outcome["result"] = asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001 — scenariot granskar felet
        outcome["error"] = exc


def _latest_draft_uid(bridge) -> int:
    return max(bridge.messages("Drafts"))


# --- Given -------------------------------------------------------------------


@given(parsers.parse('mitt konto är "{account}"'), target_fixture="ctx")
def account_ctx(account, bridge_pair, captured):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = bridge_pair[0]
    app.smtp = make_client(account)
    return ctx


@given("att Bridge inte svarar med APPENDUID")
def no_appenduid(bridge):
    bridge.appenduid = False


@given(parsers.parse('att Bridge svarar NO på "{command}"'))
def bridge_refuses(bridge, command):
    bridge.refuse[command] = "operation failed"


@given(
    parsers.parse(
        'ett mejl i INBOX från "{sender}" till "{to}" med kopia till "{cc}" och ämnet "{subject}"'
    ),
    target_fixture="original",
)
def original_message(bridge, sender, to, cc, subject):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Cc"] = cc
    msg["Subject"] = subject
    msg["Date"] = "Mon, 12 Oct 2026 09:30:00 +0200"
    msg["Message-ID"] = "<orig-1@example.se>"
    msg.set_content("Originaltext")
    uid = bridge.add("INBOX", msg.as_bytes())
    return {"uid": uid, "msg": msg}


@given(parsers.parse('att mejlet i INBOX har bilagan "{filename}"'))
def original_has_attachment(bridge, original, filename):
    msg = original["msg"]
    msg.add_attachment(b"%PDF-1.4 fejk", maintype="application", subtype="pdf", filename=filename)
    bridge.mailboxes["INBOX"][int(original["uid"])]["raw"] = msg.as_bytes()


@given(
    parsers.parse('ett utkast i Drafts till "{to}" med ämnet "{subject}" och texten "{body}"'),
    target_fixture="draft",
)
def existing_draft(bridge, to, subject, body):
    msg = EmailMessage()
    msg["From"] = "me@proton.me"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = "<draft-1@proton.me>"
    msg.set_content(body)
    return {"uid": bridge.add("Drafts", msg.as_bytes(), ("\\Draft", "\\Seen"))}


@given(
    parsers.parse(
        'ett utkast skapat till "{to}" med kopia till "{cc}" och hemlig kopia till "{bcc}"'
    ),
    target_fixture="draft",
)
def created_draft(ctx, bridge, to, cc, bcc):
    result = asyncio.run(
        create_draft(ctx, to=to, subject="Godkänt", body="Granskad text", cc=cc, bcc=bcc)
    )
    return {"uid": result["uid"], "message_id": result["message_id"]}


@given("ett utkast i Drafts utan mottagare", target_fixture="draft")
def draft_without_recipients(bridge):
    raw = (
        b"From: me@proton.me\r\nSubject: Halvfardigt\r\n"
        b"Message-ID: <tom@proton.me>\r\n\r\nText\r\n"
    )
    return {"uid": bridge.add("Drafts", raw, ("\\Draft", "\\Seen"))}


@given("att SMTP-servern vägrar alla mottagare")
def smtp_refuses_all(captured):
    for addr in ("asa@example.se", "cc@example.se", "hemlig@example.se"):
        captured.refused[addr] = (550, "no such user")


@given(parsers.parse('att SMTP-servern vägrar "{addr}"'))
def smtp_refuses(captured, addr):
    captured.refused[addr] = (550, "no such user")


# --- When --------------------------------------------------------------------


@when(
    parsers.parse(
        'jag skapar ett utkast till "{to}" med ämnet "{subject}" och texten "{body}"'
    )
)
def make_draft(ctx, outcome, to, subject, body):
    _run(outcome, create_draft(ctx, to=to, subject=subject, body=body))


@when(parsers.parse('jag skapar ett utkast till "{to}" med hemlig kopia till "{bcc}"'))
def make_draft_bcc(ctx, outcome, to, bcc):
    _run(outcome, create_draft(ctx, to=to, subject="Hej", body="Text", bcc=bcc))


@when(parsers.parse('jag skapar ett svarsutkast på mejlet i INBOX med texten "{text}"'))
def make_reply_draft(ctx, outcome, original, text):
    _run(outcome, create_reply_draft(ctx, uid=original["uid"], mailbox="INBOX", body=text))


@when(parsers.parse('jag skapar ett svara-alla-utkast på mejlet i INBOX med texten "{text}"'))
def make_reply_all_draft(ctx, outcome, original, text):
    _run(
        outcome,
        create_reply_draft(ctx, uid=original["uid"], mailbox="INBOX", body=text, reply_all=True),
    )


@when(parsers.parse('jag skapar ett svarsutkast på UID "{uid}" i INBOX med texten "{text}"'))
def make_reply_draft_uid(ctx, outcome, uid, text):
    _run(outcome, create_reply_draft(ctx, uid=uid, mailbox="INBOX", body=text))


@when(parsers.parse('jag svarar direkt på mejlet i INBOX med texten "{text}"'))
def reply_directly(ctx, original, text):
    asyncio.run(reply_to_email(ctx, uid=original["uid"], mailbox="INBOX", body=text))


@when(
    parsers.parse(
        'jag skapar ett vidarebefordringsutkast av mejlet i INBOX till "{to}" med texten "{text}"'
    )
)
def make_forward_draft(ctx, outcome, original, to, text):
    _run(
        outcome,
        create_forward_draft(ctx, uid=original["uid"], mailbox="INBOX", to=to, body=text),
    )


@when(
    parsers.parse(
        'jag uppdaterar utkastet till "{to}" med ämnet "{subject}" och texten "{body}"'
    )
)
def update_existing_draft(ctx, outcome, draft, to, subject, body):
    _run(
        outcome,
        update_draft(ctx, uid=draft["uid"], mailbox="Drafts", to=to, subject=subject, body=body),
    )


@when(
    parsers.parse(
        'jag uppdaterar utkastet med UID "{uid}" till "{to}" med ämnet "{subject}" och texten "{body}"'
    )
)
def update_draft_uid(ctx, outcome, uid, to, subject, body):
    _run(outcome, update_draft(ctx, uid=uid, mailbox="Drafts", to=to, subject=subject, body=body))


@when("jag skickar utkastet")
def send_the_draft(ctx, outcome, draft):
    _run(outcome, send_draft(ctx, uid=draft["uid"], mailbox="Drafts"))


@when(parsers.parse('jag skickar utkastet med UID "{uid}"'))
def send_draft_uid(ctx, outcome, uid):
    _run(outcome, send_draft(ctx, uid=uid, mailbox="Drafts"))


# --- Then --------------------------------------------------------------------


@then(parsers.parse("ska Drafts innehålla {count:d} utkast"))
def drafts_count(bridge, count):
    assert len(bridge.messages("Drafts")) == count


@then(parsers.parse('utkastet ska ha flaggorna "{flags}"'))
def draft_flags(bridge, flags):
    msg = bridge.messages("Drafts")[_latest_draft_uid(bridge)]
    assert msg["flags"] == set(flags.split())


@then(
    parsers.re(
        r'utkastets header "(?P<name>[^"]+)" ska innehålla "(?P<display>[^"]*)" '
        r'med adressen "(?P<addr>[^"]+)"'
    )
)
def draft_header_contains(bridge, name, display, addr):
    msg = bridge.parsed("Drafts", _latest_draft_uid(bridge))
    assert (display, addr) in header_addresses(msg, name)


@then(parsers.parse('utkastets ämne ska vara "{subject}"'))
def draft_subject(bridge, subject):
    assert bridge.parsed("Drafts", _latest_draft_uid(bridge))["Subject"] == subject


@then(parsers.parse('utkastets text ska innehålla "{text}"'))
def draft_text(bridge, text):
    msg = bridge.parsed("Drafts", _latest_draft_uid(bridge))
    assert text in msg.get_body(("plain",)).get_content()


@then("inget mejl ska ha skickats")
def nothing_sent(captured):
    assert captured.sent == []


@then('svaret ska ange mappen "Drafts", utkastets UID och dess Message-ID')
def result_points_to_draft(bridge, outcome):
    assert "error" not in outcome, outcome.get("error")
    result = outcome["result"]
    uid = _latest_draft_uid(bridge)
    assert result["mailbox"] == "Drafts"
    assert result["uid"] == str(uid)
    assert result["message_id"] == bridge.parsed("Drafts", uid)["Message-ID"]


@then(parsers.parse('ska anropet misslyckas med meddelandet "{text}"'))
def call_failed(outcome, text):
    assert "error" in outcome, f"inget fel: {outcome.get('result')!r}"
    assert text in str(outcome["error"])


@then(parsers.parse('utkastet ska sakna headern "{name}"'))
def draft_lacks_header(bridge, name):
    assert bridge.parsed("Drafts", _latest_draft_uid(bridge))[name] is None


@then(parsers.parse('utkastets header "{name}" ska vara originalets Message-ID'))
def draft_header_is_original_id(bridge, original, name):
    msg = bridge.parsed("Drafts", _latest_draft_uid(bridge))
    assert msg[name] == original["msg"]["Message-ID"]


@then("ska utkastet och det skickade svaret ha samma mottagare, ämne, trådning och text")
def draft_matches_sent(bridge, captured):
    draft = bridge.parsed("Drafts", _latest_draft_uid(bridge))
    sent = captured.parsed
    for name in ("From", "To", "Cc", "Subject", "In-Reply-To", "References"):
        assert draft[name] == sent[name], name
    assert draft.get_body(("plain",)).get_content() == sent.get_body(("plain",)).get_content()


@then(parsers.parse('utkastet ska ha bilagan "{filename}"'))
def draft_has_attachment(bridge, filename):
    msg = bridge.parsed("Drafts", _latest_draft_uid(bridge))
    assert filename in [part.get_filename() for part in msg.iter_attachments()]


@then("det gamla utkastet ska ha flyttats till Trash med UID MOVE på sitt UID")
def old_draft_trashed(bridge, draft):
    uid = draft["uid"]
    assert int(uid) not in bridge.messages("Drafts")
    assert ("UID MOVE", uid, '"Trash"') in bridge.commands
    assert len(bridge.messages("Trash")) == 1
    # Ingen permanent radering
    assert not {"UID STORE", "UID EXPUNGE", "EXPUNGE"} & set(bridge.names())


@then("inget UID STORE eller UID EXPUNGE ska ha skickats")
def no_store_or_expunge(bridge):
    assert not {"UID STORE", "UID EXPUNGE", "EXPUNGE"} & set(bridge.names())


@then("inget APPEND ska ha skickats")
def no_append(bridge):
    assert "APPEND" not in bridge.names()


@then(parsers.parse('SMTP-mottagarna ska vara "{recipients}"'))
def smtp_recipients(captured, recipients):
    assert captured.recipients == [r.strip() for r in recipients.split(",")]


@then(parsers.parse('det skickade mejlet ska sakna headern "{name}"'))
def sent_lacks_header(captured, name):
    assert captured.parsed[name] is None
    assert f"{name}:".encode() not in captured.raw


@then("det skickade mejlet ska ha utkastets ämne, text och Message-ID")
def sent_matches_draft(captured, draft):
    sent = captured.parsed
    assert sent["Subject"] == "Godkänt"
    assert "Granskad text" in sent.get_body(("plain",)).get_content()
    assert sent["Message-ID"] == draft["message_id"]
    assert sent["From"] == "me@proton.me"


@then("svaret ska ange att mejlet skickades och att utkastet togs bort")
def result_sent_and_deleted(outcome):
    assert "error" not in outcome, outcome.get("error")
    assert outcome["result"]["sent"] is True
    assert outcome["result"]["draft_deleted"] is True


@then("svaret ska ange att mejlet skickades men att utkastet ligger kvar")
def result_sent_not_deleted(outcome):
    assert "error" not in outcome, outcome.get("error")
    result = outcome["result"]
    assert result["sent"] is True
    assert result["draft_deleted"] is False
    assert "Skicka inte igen" in result["warning"]


@then("ska anropet misslyckas")
def call_failed_plain(outcome):
    assert "error" in outcome, f"inget fel: {outcome.get('result')!r}"

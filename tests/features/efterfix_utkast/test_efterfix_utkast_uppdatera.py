"""BDD-steg för efterfix_utkast_uppdatera.feature (update_draft behåller trådning och bilagor)."""
import asyncio
from email.message import EmailMessage

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.drafts import create_forward_draft, create_reply_draft, update_draft
from tests.features.efterfix_utkast.conftest import PDF, latest_draft, run

scenarios("efterfix_utkast_uppdatera.feature")

LOGO = b"\x89PNG\r\n\x1a\nfejklogga"
HTML_MED_BILD = '<html><body><p>Hej</p><img src="cid:logo-1@proton.me"></body></html>'


# --- Given -------------------------------------------------------------------


@given("ett svarsutkast på mejlet i INBOX", target_fixture="draft")
def reply_draft(ctx, original):
    result = asyncio.run(create_reply_draft(ctx, uid=original["uid"], mailbox="INBOX", body="Första svaret"))
    return {"uid": result["uid"]}


@given(parsers.parse('ett vidarebefordringsutkast av mejlet i INBOX till "{to}"'), target_fixture="draft")
def forward_draft(ctx, original, to):
    result = asyncio.run(create_forward_draft(ctx, uid=original["uid"], mailbox="INBOX", to=to))
    return {"uid": result["uid"]}


@given(
    parsers.parse('ett utkast i Drafts med HTML som visar den inbäddade bilden "{filename}"'),
    target_fixture="draft",
)
def draft_with_inline_image(bridge, filename):
    msg = EmailMessage()
    msg["From"] = "me@proton.me"
    msg["To"] = "asa@example.se"
    msg["Subject"] = "Logga"
    msg["Message-ID"] = "<draft-logo@proton.me>"
    msg.set_content("Hej")
    msg.add_alternative(HTML_MED_BILD, subtype="html")
    html = msg.get_body(("html",))
    html.add_related(LOGO, maintype="image", subtype="png", cid="<logo-1@proton.me>",
                     filename=filename)
    return {"uid": bridge.add("Drafts", msg.as_bytes(), ("\\Draft", "\\Seen"))}


@given(
    parsers.parse('ett utkast från Proton med det interna id:t "{internal_id}" som svarar på "{parent}"'),
    target_fixture="draft",
)
def proton_draft(bridge, internal_id, parent):
    # Så som Bridge visar ett utkast: X-Pm-Internal-Id, och References med
    # förälderns interna id och utkastets eget (pkg/message/build.go)
    raw = (
        "From: me@proton.me\r\nTo: anna@example.se\r\nSubject: Re: Offert\r\n"
        f"Message-ID: <{internal_id}@protonmail.internalid>\r\n"
        f"X-Pm-Internal-Id: {internal_id}\r\n"
        f"In-Reply-To: {parent}\r\n"
        f"References: {parent} <orig-pm@protonmail.internalid> "
        f"<{internal_id}@protonmail.internalid>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\nFörsta svaret\r\n"
    ).encode()
    return {"uid": bridge.add("Drafts", raw, ("\\Draft", "\\Seen"))}


# --- When --------------------------------------------------------------------


@when(parsers.parse('jag uppdaterar utkastet till "{to}" med ämnet "{subject}" och texten "{body}"'))
def update_existing(ctx, outcome, draft, to, subject, body):
    run(outcome, update_draft(ctx, uid=draft["uid"], mailbox="Drafts", to=to, subject=subject, body=body))


@when(parsers.parse('jag uppdaterar utkastet med texten "{body}" och HTML som visar samma bild'))
def update_with_html(ctx, outcome, draft, body):
    run(outcome, update_draft(ctx, uid=draft["uid"], mailbox="Drafts", to="asa@example.se",
                              subject="Logga", body=body, body_html=HTML_MED_BILD))


# --- Then --------------------------------------------------------------------


def _ok(outcome) -> dict:
    assert "error" not in outcome, outcome.get("error")
    return outcome["result"]


@then(parsers.parse('ska det nya utkastets "{name}" vara originalets Message-ID'))
def header_is_original_id(bridge, outcome, original, name):
    _ok(outcome)
    assert latest_draft(bridge)[name] == original["msg"]["Message-ID"]


@then(parsers.parse('ska det nya utkastets "{name}" innehålla originalets Message-ID'))
def header_contains_original_id(bridge, outcome, original, name):
    _ok(outcome)
    assert original["msg"]["Message-ID"] in (latest_draft(bridge)[name] or "")


@then(parsers.parse('ska det nya utkastets "{name}" vara "{value}"'))
def header_is(bridge, outcome, name, value):
    _ok(outcome)
    assert latest_draft(bridge)[name] == value


@then(parsers.parse('utkastet ska ha bilagan "{filename}" med originalets innehåll'))
def has_original_attachment(bridge, outcome, filename):
    _ok(outcome)
    parts = {p.get_filename(): p for p in latest_draft(bridge).iter_attachments()}
    assert filename in parts, list(parts)
    assert parts[filename].get_content() == PDF


@then(parsers.parse('utkastet ska ha bilagan "{filename}"'))
def has_attachment(bridge, outcome, filename):
    _ok(outcome)
    names = [p.get_filename() for p in latest_draft(bridge).iter_attachments()]
    assert filename in names, names


@then(parsers.parse('ska bilden "{filename}" ligga i samma multipart/related som HTML-delen'))
def image_related_to_html(bridge, outcome, filename):
    _ok(outcome)
    msg = latest_draft(bridge)
    related = [p for p in msg.walk() if p.get_content_type() == "multipart/related"]
    assert len(related) == 1
    children = list(related[0].iter_parts())
    assert children[0].get_content_type() == "text/html"
    images = [p for p in children[1:] if p.get_filename() == filename]
    assert images and images[0].get_content() == LOGO
    assert images[0]["Content-ID"] == "<logo-1@proton.me>"


@then(parsers.parse('svaret ska ange att rubrikerna "{names}" behölls'))
def result_kept_headers(outcome, names):
    assert _ok(outcome)["kept_headers"] == [n.strip() for n in names.split(",")]


@then(parsers.parse('svaret ska ange att bilagan "{filename}" behölls'))
def result_kept_attachment(outcome, filename):
    assert filename in _ok(outcome)["kept_attachments"]


@then("det gamla utkastet ska ligga i Trash")
def old_in_trash(bridge, outcome, draft):
    _ok(outcome)
    assert ("UID MOVE", draft["uid"], '"Trash"') in bridge.commands
    trashed = [bridge.parsed("Trash", uid) for uid in bridge.messages("Trash")]
    assert len(trashed) == 1
    assert "Första svaret" in trashed[0].get_body(("plain",)).get_content()


@then(parsers.parse('svaret ska ange att det gamla utkastet flyttades till "{mailbox}"'))
def result_moved_to(outcome, draft, mailbox):
    result = _ok(outcome)
    assert result["replaced_uid"] == draft["uid"]
    assert result["replaced_moved_to"] == mailbox


@given(parsers.parse("att Bridge {avbrott} vid UID MOVE"))
def bridge_breaks_on_move(bridge, avbrott):
    errors = {
        "inte svarar i tid": asyncio.TimeoutError(),
        "tappar anslutningen": ConnectionResetError("Connection lost"),
    }
    inner = bridge.client.uid.side_effect

    async def uid(command, *args):
        if command.upper() == "MOVE":
            bridge.commands.append(("UID MOVE", *args))
            raise errors[avbrott]
        return await inner(command, *args)

    bridge.client.uid.side_effect = uid


@then("felet ska ange det nya utkastets UID och Message-ID")
def error_names_new_draft(bridge, outcome, draft):
    text = str(outcome["error"])
    new_uid = max(bridge.messages("Drafts"))
    assert f"UID {new_uid}" in text
    assert bridge.parsed("Drafts", new_uid)["Message-ID"] in text
    assert f"UID {draft['uid']}" in text


@then("felet ska säga att update_draft inte ska köras igen")
def error_says_do_not_retry(outcome):
    assert "Kör inte update_draft igen" in str(outcome["error"])

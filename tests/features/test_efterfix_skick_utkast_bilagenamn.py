"""BDD-steg för efterfix_skick_utkast_bilagenamn.feature."""
import asyncio
import email
import email.policy
import re
from email.message import EmailMessage
from unittest.mock import MagicMock

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools import drafts
from tests.feat_utkast_bridge import make_imap
from tests.fix_svar_support import make_client

scenarios("efterfix_skick_utkast_bilagenamn.feature")


def _decode(text: str) -> str:
    return re.sub(r"\[U\+([0-9A-Fa-f]{4,6})\]", lambda m: chr(int(m.group(1), 16)), text)


@given(parsers.parse('ett utkast i Drafts med bilagan "{filename}"'), target_fixture="draft")
def draft_with_attachment(filename):
    imap, bridge = make_imap()
    old = EmailMessage()
    old["From"] = "me@proton.me"
    old["To"] = "a@example.se"
    old["Subject"] = "Fwd: faktura"
    old.set_content("Se bilagan")
    name = _decode(filename)
    old.add_attachment(b"MZ", maintype="application", subtype="octet-stream", filename=name)
    uid = bridge.add("Drafts", old.as_bytes(), ("\\Draft", "\\Seen"))
    return {"imap": imap, "bridge": bridge, "uid": uid, "name": name}


@when("LLM:en ersätter utkastet med update_draft", target_fixture="result")
def update(draft):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.smtp = make_client("me@proton.me")
    app.imap = draft["imap"]
    return asyncio.run(drafts.update_draft(
        ctx, uid=draft["uid"], mailbox="Drafts", to="a@example.se", subject="Fwd: faktura", body="Ny text",
    ))


@then(parsers.parse('ska kept_attachments vara "{names}"'))
def kept(result, names):
    assert result["kept_attachments"] == [n.strip() for n in names.split(",")]


@then("ska bilagan i det nya utkastet ha kvar sitt ursprungliga namn")
def original_name_kept(draft, result):
    raw = draft["bridge"].messages("Drafts")[int(result["uid"])]["raw"]
    new = email.message_from_bytes(raw, policy=email.policy.default)
    (part,) = list(new.iter_attachments())
    assert part.get_filename() == draft["name"]
    assert part.get_content() == b"MZ"

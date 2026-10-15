"""BDD-steg för efterfix_utkast_skicka_mottagare.feature (send_draft och dolda mottagare)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then

from protonmail_mcp.tools.messages import get_email

scenarios("efterfix_utkast_skicka_mottagare.feature")


def _header(name: str, value: str) -> str:
    return f"{name}: {value}\r\n" if value else ""


@given(
    parsers.re(
        r'ett utkast i Drafts till "(?P<to>(?:[^"\\]|\\.)*)" med kopia "(?P<cc>(?:[^"\\]|\\.)*)" '
        r'och hemlig kopia "(?P<bcc>(?:[^"\\]|\\.)*)"'
    ),
    target_fixture="draft",
)
def raw_draft(bridge, to, cc, bcc):
    unescape = lambda v: v.replace('\\"', '"')  # noqa: E731
    raw = (
        "From: me@proton.me\r\n"
        + _header("To", unescape(to))
        + _header("Cc", unescape(cc))
        + _header("Bcc", unescape(bcc))
        + "Subject: Rapport\r\nMessage-ID: <rapport-1@proton.me>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\nHej\r\n"
    ).encode("utf-8")
    return {"uid": bridge.add("Drafts", raw, ("\\Draft", "\\Seen")), "raw": raw}


@given(parsers.parse('att utkastet har en extra rubrik "{line}"'))
def extra_header(bridge, draft, line):
    entry = bridge.messages("Drafts")[int(draft["uid"])]
    head, _, body = entry["raw"].partition(b"\r\n\r\n")
    entry["raw"] = head + b"\r\n" + line.encode() + b"\r\n\r\n" + body


@then(parsers.parse('SMTP-mottagarna ska vara "{recipients}"'))
def smtp_recipients(captured, recipients):
    assert captured.recipients == [r.strip() for r in recipients.split(",")]


@then(parsers.parse('svaret ska ange mottagarna to "{to}", cc "{cc}" och bcc "{bcc}"'))
def result_recipients(outcome, to, cc, bcc):
    assert "error" not in outcome, outcome.get("error")
    assert outcome["result"]["recipients"] == {"to": [to], "cc": [cc], "bcc": [bcc]}


@then("get_email på utkastet ska ha visat samma mottagare som skickades")
def shown_equals_sent(ctx, bridge, draft, outcome):
    # Utkastet är borta ur Drafts efter skicket; granska samma råtext igen
    uid = bridge.add("INBOX", draft["raw"])
    shown = asyncio.run(get_email(ctx, uid=uid, mailbox="INBOX"))["addresses"]
    assert {k: [a for _, a in shown[k]] for k in ("to", "cc", "bcc")} == outcome["result"]["recipients"]

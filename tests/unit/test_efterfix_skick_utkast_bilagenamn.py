"""update_draft:s kept_attachments har rensade bilagenamn (granskning 3, injektion F5)."""
from email.message import EmailMessage

from protonmail_mcp.tools.drafts import _kept_from_old


def _draft(*attachments):
    msg = EmailMessage()
    msg["From"] = "me@proton.me"
    msg["To"] = "a@example.se"
    msg["Subject"] = "x"
    msg.set_content("text")
    for name, ctype in attachments:
        maintype, subtype = ctype.split("/")
        msg.add_attachment(b"data", maintype=maintype, subtype=subtype, filename=name)
    return msg.as_bytes()


def test_kept_attachment_names_are_cleaned():
    raw = _draft(("faktura‮fdp.exe\U000E0049\U000E0047", "application/octet-stream"))
    fields, summary = _kept_from_old(raw, None)
    assert summary["kept_attachments"] == ["fakturafdp.exe"]
    # själva bilagan följer med oförändrad
    (part,) = fields["attachments"]
    assert part.get_filename() == "faktura‮fdp.exe\U000E0049\U000E0047"


def test_rfc2047_encoded_name_is_decoded_and_cleaned():
    raw = (
        b"From: me@proton.me\r\nTo: a@example.se\r\nSubject: x\r\nMIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="B"\r\n\r\n'
        b"--B\r\nContent-Type: text/plain\r\n\r\ntext\r\n"
        b"--B\r\nContent-Type: application/octet-stream\r\n"
        b'Content-Disposition: attachment; filename="=?utf-8?b?' + __import__("base64").b64encode(
            "räkning​.pdf".encode()) + b'?="\r\n\r\ndata\r\n--B--\r\n'
    )
    _, summary = _kept_from_old(raw, None)
    assert summary["kept_attachments"] == ["räkning.pdf"]


def test_name_that_is_only_hidden_characters_falls_back_to_content_type():
    raw = _draft(("‮​", "application/pdf"))
    _, summary = _kept_from_old(raw, None)
    assert summary["kept_attachments"] == ["application/pdf"]

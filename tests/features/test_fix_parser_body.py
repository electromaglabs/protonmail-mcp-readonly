"""BDD-tester för brödtext och bilagor (fix-parser)."""
import asyncio

from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.tools.messages import get_email

scenarios("fix_parser_body.feature")


def _serve(mock_ctx, raw: bytes) -> bytes:
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@given(
    parsers.parse("ett multipart/alternative-mejl med {size:d} tecken HTML"),
    target_fixture="raw",
)
def newsletter(mock_ctx, size):
    html = "<html><body>" + "x" * size + "</body></html>"
    raw = (
        "From: news@x.se\r\nSubject: Nyhetsbrev\r\nMIME-Version: 1.0\r\n"
        'Content-Type: multipart/alternative; boundary="b"\r\n\r\n'
        "--b\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nKort text\r\n"
        f"--b\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{html}\r\n--b--\r\n"
    ).encode()
    return _serve(mock_ctx, raw)


@when("jag hämtar mejlet med get_email med förvalda parametrar", target_fixture="result")
def fetch_default(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1"))


@when(
    parsers.parse('jag hämtar mejlet med get_email och body_format "{fmt}"'),
    target_fixture="result",
)
def fetch_with_format(mock_ctx, raw, fmt):
    return asyncio.run(get_email(mock_ctx, uid="1", body_format=fmt))


@then(parsers.parse("ska body_html vara högst {n:d} tecken"))
def html_at_most(result, n):
    assert len(result["body_html"]) <= n


@then(parsers.parse("body_plain ska vara högst {n:d} tecken"))
def plain_at_most(result, n):
    assert len(result["body_plain"]) <= n


@then(parsers.parse("ska body_html vara minst {n:d} tecken"))
def html_at_least(result, n):
    assert len(result["body_html"]) >= n


_PDF = "Content-Type: application/pdf\r\nContent-Transfer-Encoding: base64\r\n"
_PDF_DATA = "JVBERi0xLjQKJcOkw7zDtsOfCg==\r\n"  # "%PDF-1.4\n%äüöß\n"


def _mixed(*parts: str) -> bytes:
    body = "".join(f"--b\r\n{p}\r\n" for p in parts)
    return (
        "From: a@b.se\r\nSubject: s\r\nMIME-Version: 1.0\r\n"
        f'Content-Type: multipart/mixed; boundary="b"\r\n\r\n{body}--b--\r\n'
    ).encode()


@given(
    "ett HTML-mejl med ett bifogat vidarebefordrat mejl som har en egen bilaga",
    target_fixture="raw",
)
def forwarded_mail(mock_ctx):
    inner = (
        "From: c@d.se\r\nSubject: inre\r\nMIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="i"\r\n\r\n'
        "--i\r\nContent-Type: text/plain\r\n\r\nInre text\r\n"
        f'--i\r\n{_PDF}Content-Disposition: attachment; filename="inre.pdf"\r\n\r\n{_PDF_DATA}'
        "--i--\r\n"
    )
    raw = _mixed(
        "Content-Type: text/html; charset=utf-8\r\n\r\n<p>Yttre text</p>",
        "Content-Type: message/rfc822\r\n\r\n" + inner,
    )
    return _serve(mock_ctx, raw)


@given(
    parsers.parse(
        'ett mejl med brödtexten "{text}" och en PDF märkt "{disposition}"'
    ),
    target_fixture="raw",
)
def mail_with_pdf(mock_ctx, text, disposition):
    disposition = disposition.replace('\\"', '"')
    raw = _mixed(
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n{text}",
        f"{_PDF}Content-Disposition: {disposition}\r\n\r\n{_PDF_DATA}",
    )
    return _serve(mock_ctx, raw)


@given(
    parsers.parse(
        'ett mejl med brödtexten "{text}" och en textbilaga märkt "{disposition}"'
    ),
    target_fixture="raw",
)
def mail_with_text_attachment(mock_ctx, text, disposition):
    disposition = disposition.replace('\\"', '"')
    raw = _mixed(
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n{text}",
        f"Content-Type: text/plain\r\nContent-Disposition: {disposition}\r\n\r\nloggrad 1",
    )
    return _serve(mock_ctx, raw)


@given("ett mejl som bara är en PDF", target_fixture="raw")
def pdf_only(mock_ctx):
    raw = (f"From: scanner@x.se\r\nSubject: Skanning\r\nMIME-Version: 1.0\r\n{_PDF}\r\n{_PDF_DATA}").encode()
    return _serve(mock_ctx, raw)


@given(
    parsers.parse('ett multipart/mixed-mejl med HTML-delarna "{first}" och "{second}" runt en bild'),
    target_fixture="raw",
)
def apple_mail_html(mock_ctx, first, second):
    raw = _mixed(
        f"Content-Type: text/html; charset=utf-8\r\n\r\n<html><body>{first}",
        'Content-Type: image/png; name="bild.png"\r\nContent-Disposition: inline; '
        'filename="bild.png"\r\nContent-Transfer-Encoding: base64\r\n\r\niVBORw0KGgo=',
        f"Content-Type: text/html; charset=utf-8\r\n\r\n{second}</body></html>",
    )
    return _serve(mock_ctx, raw)


@then(parsers.parse('ska body_plain inte innehålla "{text}"'))
@then(parsers.parse('body_plain ska inte innehålla "{text}"'))
def plain_not_contains(result, text):
    assert text not in result["body_plain"]


@then(parsers.parse('body_plain ska innehålla "{text}"'))
def plain_contains(result, text):
    assert text in result["body_plain"]


@then(parsers.parse('ska body_html innehålla "{text}"'))
@then(parsers.parse('body_html ska innehålla "{text}"'))
def html_contains(result, text):
    assert text in result["body_html"]


@then(parsers.parse('bilagorna ska vara exakt "{content_type}"'))
def attachments_exactly(result, content_type):
    assert [a["content_type"] for a in result["attachments"]] == [content_type]


@then(parsers.parse('ska bilagornas filnamn vara "{filename}"'))
def attachment_filenames(result, filename):
    assert [a["filename"] for a in result["attachments"]] == [filename]


@then("ska body_plain vara tom")
def plain_empty(result):
    assert result["body_plain"] == ""


def _html_only(html: str) -> bytes:
    return (
        "From: a@b.se\r\nSubject: s\r\nMIME-Version: 1.0\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n\r\n{html}\r\n"
    ).encode()


@given("ett HTML-mejl utan textdel med stilmall, entiteter och stycken", target_fixture="raw")
def styled_html(mock_ctx):
    html = (
        "<html><head><style>p { color: red }</style></head><body>"
        "<p>Hej &amp; välkommen</p><div>Rad 1</div><div>Rad 2</div></body></html>"
    )
    return _serve(mock_ctx, _html_only(html))


@given(
    parsers.parse('ett HTML-mejl utan textdel med svaret "{reply}" och citatet "{quote}"'),
    target_fixture="raw",
)
def html_reply(mock_ctx, reply, quote):
    html = f"<div>{reply}</div><blockquote><div>{quote}</div></blockquote>"
    return _serve(mock_ctx, _html_only(html))


@then(parsers.parse('"{first}" och "{second}" ska stå på olika rader i body_plain'))
def on_separate_lines(result, first, second):
    lines = result["body_plain"].splitlines()
    assert any(first in line for line in lines)
    assert not any(first in line and second in line for line in lines)


@given(
    parsers.parse('ett multipart/alternative-mejl med textdelen "{plain}" och HTML-delen "{html}"'),
    target_fixture="raw",
)
def alternative_mail(mock_ctx, plain, html):
    raw = (
        "From: a@b.se\r\nSubject: s\r\nMIME-Version: 1.0\r\n"
        'Content-Type: multipart/alternative; boundary="b"\r\n\r\n'
        f"--b\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{plain}\r\n"
        f"--b\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{html}\r\n--b--\r\n"
    ).encode()
    return _serve(mock_ctx, raw)


def _try(coro):
    try:
        return asyncio.run(coro)
    except ValueError as exc:
        return exc


@when(parsers.parse('jag försöker hämta mejlet med body_format "{fmt}"'), target_fixture="result")
def try_format(mock_ctx, raw, fmt):
    return _try(get_email(mock_ctx, uid="1", body_format=fmt))


@when(parsers.parse("jag försöker hämta mejlet med max_length {n:d}"), target_fixture="result")
def try_max_length(mock_ctx, raw, n):
    return _try(get_email(mock_ctx, uid="1", max_length=n))


@then(parsers.parse('ska anropet avvisas med ett fel som nämner "{word}"'))
def rejected(result, word):
    assert isinstance(result, ValueError)
    assert word in str(result)

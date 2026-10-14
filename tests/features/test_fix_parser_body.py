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

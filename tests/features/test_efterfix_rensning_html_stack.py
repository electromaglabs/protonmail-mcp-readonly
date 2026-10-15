"""BDD: gömd HTML tolkas som i en webbläsare (efterfix-rensning, F8a/b, F10)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.messages import get_email

scenarios("efterfix_rensning_html_stack.feature")


def _serve(mock_ctx, html: str) -> bytes:
    raw = f"From: a@b.se\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{html}\r\n".encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@given(parsers.parse("ett HTML-mejl med innehållet '{html}'"), target_fixture="raw")
def html_mail(mock_ctx, html):
    return _serve(mock_ctx, html)


@given(
    parsers.parse(
        'ett HTML-mejl med {n:d} nästlade stilade element runt ett element med stilen "{style}" som innehåller "{text}"'
    ),
    target_fixture="raw",
)
def nested(mock_ctx, n, style, text):
    html = "<p>Hej</p>" + "<span style='color:red'>" * n + f"<i style='{style}'>{text}</i>" + "</span>" * n
    return _serve(mock_ctx, html)


@when("jag hämtar mejlet som text med get_email", target_fixture="result")
def fetch(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX", max_length=None))


@then(parsers.parse('ska brödtexten innehålla "{text}"'))
def contains(result, text):
    assert text in result["body_plain"]


@then(parsers.parse('ska brödtexten inte innehålla "{text}"'))
def not_contains(result, text):
    assert text not in result["body_plain"]


@then(parsers.parse('ska brödtexten vara "{text}"'))
def body_is(result, text):
    assert result["body_plain"] == text

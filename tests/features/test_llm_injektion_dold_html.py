"""BDD: dold HTML-text når inte modellen (llm-injektion)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.messages import get_email

scenarios("llm_injektion_dold_html.feature")


@given(parsers.parse("ett HTML-mejl med innehållet '{html}'"), target_fixture="raw")
def html_mail(mock_ctx, html):
    raw = f"From: a@b.se\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{html}\r\n".encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@given(
    parsers.parse(
        'ett HTML-mejl med "{before}" och "{after}" runt ett element med stilen "{style}" som innehåller "{hidden}"'
    ),
    target_fixture="raw",
)
def html_mail_with_styled_element(mock_ctx, before, after, style, hidden):
    return html_mail(mock_ctx, f'<p>{before}</p><div style="{style}">{hidden}</div><p>{after}</p>')


@when("jag hämtar mejlet som text med get_email", target_fixture="result")
def fetch(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX", max_length=None))


@then(parsers.parse('ska brödtexten vara "{body}"'))
def body_is(result, body):
    assert result["body_plain"] == body.replace("\\n", "\n")

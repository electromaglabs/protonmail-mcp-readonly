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


@when(parsers.parse('jag hämtar mejlet som "{body_format}" med get_email'), target_fixture="result")
def fetch_as(mock_ctx, raw, body_format):
    return asyncio.run(
        get_email(mock_ctx, uid="1", mailbox="INBOX", body_format=body_format, max_length=None)
    )


@then(parsers.parse('ska "{text}" inte finnas i något fält i svaret'))
def nowhere(result, text):
    import json

    assert text not in json.dumps(result, ensure_ascii=False)


@then("ska body_html saknas i svaret")
def no_body_html(result):
    assert result["body_html"] is None


@then("ska has_html vara sant")
def has_html(result):
    assert result["has_html"] is True


@then(parsers.parse('ska body_html innehålla "{text}"'))
def body_html_contains(result, text):
    assert text in result["body_html"]


@then("ska hidden_html räkna 1 gömt element")
def one_hidden(result):
    assert result["hidden_html"]["elements"] == 1


@then("ska suspicious_content nämna gömd text i body_html")
def flags_hidden_html(result):
    assert any("body_html" in r and "gömd" in r for r in result["suspicious_content"])


@then("ska suspicious_content nämna taggtecken")
def flags_tags(result):
    assert any("taggtecken" in r for r in result["suspicious_content"])

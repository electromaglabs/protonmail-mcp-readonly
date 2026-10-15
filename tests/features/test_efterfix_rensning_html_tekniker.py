"""BDD: fler sätt att gömma text i HTML fångas (efterfix-rensning, F9)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.messages import get_email

scenarios("efterfix_rensning_html_tekniker.feature")


@given(parsers.parse("ett HTML-mejl med innehållet '{html}'"), target_fixture="raw")
def html_mail(mock_ctx, html):
    raw = f"From: a@b.se\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{html}\r\n".encode()
    mock_ctx.request_context.lifespan_context.imap.get_message.return_value = raw
    return raw


@when("jag hämtar mejlet som text med get_email", target_fixture="result")
def fetch(mock_ctx, raw):
    return asyncio.run(get_email(mock_ctx, uid="1", mailbox="INBOX", max_length=None))


@then(parsers.parse('ska brödtexten vara "{text}"'))
def body_is(result, text):
    assert result["body_plain"] == text


@then("ska hidden_html räkna minst 1 gömt element")
def counted(result):
    assert result["hidden_html"]["elements"] >= 1

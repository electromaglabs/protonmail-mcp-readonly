"""BDD: get_email_headers har nycklarna message_id/reply_to som get_email (efterfix-verktyg, K6)."""
import asyncio

from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.tools.messages import get_email_headers

scenarios("efterfix_verktyg_header_nycklar.feature")


@given(parsers.parse(
    'att brevet med UID "{uid}" i "{mailbox}" har Message-ID "{msgid}" och Reply-To "{reply_to}"'
))
def message_with_headers(mock_ctx, uid, mailbox, msgid, reply_to):
    # Samma form som IMAPClient._parse_headers ger: gemener, bindestreck kvar
    mock_ctx.request_context.lifespan_context.imap.get_message_headers.return_value = {
        "from": "a@ex.se",
        "subject": "Hej",
        "message-id": msgid,
        "reply-to": reply_to,
    }


@when(parsers.parse('jag hämtar headers för brevet med UID "{uid}" i "{mailbox}"'),
      target_fixture="result")
def fetch_headers(mock_ctx, uid, mailbox):
    return asyncio.run(get_email_headers(mock_ctx, uid=uid, mailbox=mailbox))


@then(parsers.parse('ska svaret ha {key} "{value}"'))
def has_key(result, key, value):
    assert result.get(key) == value


@then("ska inga nycklar i svaret innehålla bindestreck")
def no_dashes(result):
    assert not [k for k in result if "-" in k]

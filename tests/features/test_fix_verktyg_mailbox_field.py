"""BDD-tester: list/search/get anger mailbox för varje brev (fix-verktyg, N5)."""
import asyncio

from pytest_bdd import scenarios, given, when, then, parsers

from protonmail_mcp.tools.messages import get_email, list_emails
from protonmail_mcp.tools.search import search_emails

scenarios("fix_verktyg_mailbox_field.feature")


def _imap(mock_ctx):
    return mock_ctx.request_context.lifespan_context.imap


@given(parsers.parse('att etiketten "{mailbox}" innehåller brevet med UID "{uid}"'))
def label_contains(mock_ctx, mailbox, uid):
    _imap(mock_ctx).list_messages.return_value = {
        "messages": [{"uid": uid, "subject": "Kvitto"}],
        "total": 1, "page": 1, "pages": 1, "has_more": False,
    }


@given(parsers.parse('att sökning i "{mailbox}" ger brevet med UID "{uid}"'))
def search_hits(mock_ctx, mailbox, uid):
    _imap(mock_ctx).search_messages.return_value = [{"uid": uid, "subject": "Viktigt"}]


@given(parsers.parse('att brevet med UID "{uid}" finns i "{mailbox}"'))
def message_in(mock_ctx, sample_raw_email, uid, mailbox):
    _imap(mock_ctx).get_message.return_value = sample_raw_email


@when(parsers.parse('jag listar brev i "{mailbox}"'), target_fixture="result")
def do_list(mock_ctx, mailbox):
    return asyncio.run(list_emails(mock_ctx, mailbox=mailbox))


@when(parsers.parse('jag söker brev i "{mailbox}"'), target_fixture="result")
def do_search(mock_ctx, mailbox):
    return asyncio.run(search_emails(mock_ctx, mailbox=mailbox))


@when(parsers.parse('jag hämtar brevet med UID "{uid}" ur "{mailbox}"'), target_fixture="result")
def do_get(mock_ctx, uid, mailbox):
    return asyncio.run(get_email(mock_ctx, uid=uid, mailbox=mailbox))


@then(parsers.parse('ska varje brev i listan ha mailbox "{mailbox}"'))
def each_listed(result, mailbox):
    assert result["messages"]
    assert all(m["mailbox"] == mailbox for m in result["messages"])


@then(parsers.parse('svaret ska ange mailbox "{mailbox}"'))
def envelope_mailbox(result, mailbox):
    assert result["mailbox"] == mailbox


@then(parsers.parse('ska varje sökträff ha mailbox "{mailbox}"'))
def each_hit(result, mailbox):
    assert result
    assert all(m["mailbox"] == mailbox for m in result)


@then(parsers.parse('ska brevet ha mailbox "{mailbox}"'))
def message_mailbox(result, mailbox):
    assert result["mailbox"] == mailbox

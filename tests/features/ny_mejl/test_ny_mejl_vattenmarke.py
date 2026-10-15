"""BDD: vattenmärket för nya mejl går inte att förgifta (ny-mejl, säkerhetsgranskning)."""
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools import new_mail
from tests.features.ny_mejl.conftest import run

scenarios("ny_mejl_vattenmarke.feature")


@given("att jag har anropat check_new_emails för INBOX")
def checked(env):
    env.result = run(env, new_mail.check_new_emails(env.ctx, mailbox="INBOX"))


@when(parsers.parse('jag anropar check_new_emails för "{mailbox}" med since_uid "{uid}"'))
def check_other(env, mailbox, uid):
    run(env, new_mail.check_new_emails(env.ctx, mailbox=mailbox, since_uid=uid))


@then(parsers.parse("ska vattenmärket för INBOX vara UID {uid:d}"))
def mark_is(env, uid):
    assert env.app.watcher.marks["INBOX"][1] == uid
    assert env.result["timed_out"] is True

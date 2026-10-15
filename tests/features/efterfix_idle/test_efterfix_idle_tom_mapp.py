"""BDD: verktygen och bevakningen i en tom mapp (G4I-3)."""
import time

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools import new_mail
from tests.features.efterfix_idle.conftest import eventually, run, start_watcher, wait_watching

scenarios("efterfix_idle_tom_mapp.feature")


@given(parsers.parse('att Bridge har den tomma mappen "{empty}" och mappen "{other}" med mejlet {uid:d}'))
def boxes(env, empty, other, uid):
    env.fake.add_box(empty, [])
    env.fake.add_box(other, [uid])


@given("att servern bara bevakar INBOX")
def watch_inbox(env):
    start_watcher(env, mailboxes="INBOX")
    wait_watching(env)


@given(parsers.parse('att servern bevakar "{mailbox}"'))
def watch_box(env, mailbox):
    start_watcher(env, mailboxes=mailbox)
    wait_watching(env, mailbox)


@given(parsers.parse('att check_new_emails har anropats för "{mailbox}"'))
def checked(env, mailbox):
    run(env, new_mail.check_new_emails(env.ctx, mailbox=mailbox))


@when(parsers.parse('jag anropar check_new_emails för "{mailbox}"'))
def check(env, mailbox):
    try:
        env.result = run(env, new_mail.check_new_emails(env.ctx, mailbox=mailbox))
    except Exception as exc:  # noqa: BLE001 — scenariot kontrollerar felet
        env.error = exc


@when(parsers.parse('jag väntar på nya mejl i "{mailbox}" i högst {timeout:d} sekunder'))
def wait(env, mailbox, timeout):
    env.monkeypatch.setattr(new_mail, "POLL_INTERVAL", 0.2)
    begin = time.monotonic()
    try:
        env.result = run(env, new_mail.wait_for_new_email(env.ctx, mailbox=mailbox, timeout_seconds=timeout))
    except Exception as exc:  # noqa: BLE001
        env.error = exc
    env.elapsed = time.monotonic() - begin


@when(parsers.parse('ett mejl kommer till "{mailbox}" och flyttas bort innan bevakningen hinner söka'))
def deliver_and_vanish(env, mailbox):
    searches = len([1 for _, line in env.fake.commands if "UID SEARCH" in line.upper()])
    uid = env.fake.deliver(mailbox, subject="Filtreras bort")
    env.fake.remove(mailbox, uid)
    eventually(env, lambda: len([1 for _, line in env.fake.commands if "UID SEARCH" in line.upper()])
               > searches, what="bevakningens sökning")


@when(parsers.parse('ett mejl med ämnet "{subject}" kommer till "{mailbox}"'))
def deliver(env, subject, mailbox):
    env.fake.deliver(mailbox, subject=subject)


@when(parsers.parse('mejlet {uid:d} flyttas bort ur "{mailbox}"'))
def vanish(env, uid, mailbox):
    env.fake.remove(mailbox, uid)


@when("Bridge startas om")
def restart(env):
    env.connections_before_restart = env.fake.connections_total
    run(env, env.fake.drop_all())


@then("ska väntan ha gått ut utan fel")
def timed_out(env):
    assert env.error is None, env.error
    assert env.result["timed_out"] is True
    assert env.result["messages"] == []


@then(parsers.parse('ska bevakningen fortfarande bevaka "{mailbox}" utan fel'))
def still_watching(env, mailbox):
    run(env, __import__("asyncio").sleep(0.3))
    assert env.watcher.status(mailbox)["last_error"] is None
    assert env.watcher.is_watching(mailbox)


@then(parsers.parse('ska händelsekön för "{mailbox}" innehålla mejlet med ämnet "{subject}"'))
def queue_has(env, mailbox, subject):
    eventually(env, lambda: subject in [m["subject"] for m in env.watcher.recent_events(mailbox)],
               timeout=2, what=f"mejlet {subject!r} i kön")


@then(parsers.parse('ska bevakningen ha återanslutit till "{mailbox}" utan fel'))
def reconnected(env, mailbox):
    eventually(env, lambda: env.fake.connections_total > env.connections_before_restart
               and env.watcher.is_watching(mailbox), timeout=4, what="återanslutningen")
    assert env.watcher.status(mailbox)["last_error"] is None

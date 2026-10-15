"""BDD: UIDVALIDITY-byte som bevakningen upptäcker (G4I-4)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools import new_mail
from tests.features.efterfix_idle.conftest import eventually, run, start_watcher, wait_watching

scenarios("efterfix_idle_uidvalidity.feature")


@given(parsers.parse("att servern bevakar INBOX och försöker igen efter {seconds:f} sekunder"))
def watching(env, seconds):
    async def sleep(delay):
        env.delays.append(delay)
        await asyncio.sleep(seconds)

    start_watcher(env, sleep=sleep)
    wait_watching(env)


def _seen(env, subject):
    return subject in [m["subject"] for m in env.watcher.recent_events("INBOX")]


@given(parsers.parse('att ett mejl med ämnet "{subject}" har kommit och visats av check_new_emails'))
def shown_before(env, subject):
    env.fake.deliver("INBOX", subject=subject)
    eventually(env, lambda: _seen(env, subject), what=f"mejlet {subject!r}")
    result = run(env, new_mail.check_new_emails(env.ctx, mailbox="INBOX"))
    assert [m["subject"] for m in result["messages"]] == [subject]


def _outage(env, subjects):
    env.connections_before_restart = env.fake.connections_total

    def during():
        box = env.fake.boxes["INBOX"]
        env.fake.renumber("INBOX", uidvalidity=2, uids=[100 + i for i in range(len(box.messages))])
        for subject in subjects:
            env.fake.deliver("INBOX", subject=subject)

    run(env, env.fake.outage(during))


@when(parsers.parse(
    'Bridge är nere en stund, numrerar om INBOX och mejl med ämnena "{subjects}" kommer under tiden'
))
def outage_with_mail(env, subjects):
    _outage(env, subjects.split(","))


@when("Bridge är nere en stund och numrerar om INBOX")
def outage_without_mail(env):
    _outage(env, [])


@when("bevakningen har återanslutit")
def reconnected(env):
    eventually(env, lambda: env.fake.connections_total > env.connections_before_restart
               and env.watcher.is_watching("INBOX") and env.watcher.uidvalidity("INBOX") == 2,
               what="återanslutningen")


@when(parsers.parse('ett mejl med ämnet "{subject}" kommer till INBOX och bevakningen har sett det'))
def deliver_seen(env, subject):
    env.fake.deliver("INBOX", subject=subject)
    eventually(env, lambda: _seen(env, subject), what=f"mejlet {subject!r}")


@when(parsers.parse("jag väntar på nya mejl i INBOX i högst {timeout:d} sekunder"))
def wait(env, timeout):
    env.result = run(env, new_mail.wait_for_new_email(env.ctx, mailbox="INBOX", timeout_seconds=timeout))


@then(parsers.parse('ska svaret innehålla mejlen med ämnena "{subjects}"'))
def has_subjects(env, subjects):
    assert env.error is None, env.error
    assert [m["subject"] for m in env.result["messages"]] == subjects.split(","), env.result


@then("ska svaret inte ha någon anteckning")
def no_note(env):
    assert env.result["note"] is None, env.result["note"]

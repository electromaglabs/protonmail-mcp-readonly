"""BDD: lyssnarna anropas utan att bevakningen väntar på dem (R4-3)."""
import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from tests.features.efterfix_idle.conftest import eventually, run, start_watcher, wait_watching

scenarios("efterfix_idle_lyssnare.feature")


@given("att bevakningen av INBOX har startat med en lyssnare som hänger sig")
def hanging_listener(env):
    start_watcher(env, renew_seconds=60)
    env.calls, env.cancelled = [], []

    async def hangs(mailbox, messages):
        env.calls.append([m["subject"] for m in messages])
        try:
            await asyncio.Event().wait()  # som en session som slutat läsa
        except asyncio.CancelledError:
            env.cancelled.append(True)
            raise

    env.watcher._listeners.insert(0, hangs)
    wait_watching(env)


@when(parsers.parse('ett mejl med ämnet "{subject}" kommer till INBOX och lyssnaren har anropats'))
def deliver_and_called(env, subject):
    env.fake.deliver("INBOX", subject=subject)
    eventually(env, lambda: [subject] in env.calls, what="lyssnaranropet")


@when(parsers.parse('ett mejl med ämnet "{subject}" kommer till INBOX'))
def deliver(env, subject):
    env.fake.deliver("INBOX", subject=subject)


@when("bevakningen stoppas")
def stop(env):
    env.notify_tasks = set(env.watcher._notify_tasks)
    run(env, env.watcher.stop(), timeout=5)


@then("ska lyssnaren ha anropats för båda mejlen")
def called_for_both(env):
    eventually(env, lambda: len(env.calls) == 2, timeout=1, what="två lyssnaranrop")
    assert env.calls == [["Först"], ["Sedan"]]


@then("ska lyssnaranropet ha avbrutits")
def listener_cancelled(env):
    assert env.cancelled == [True]


@then("ska inga bevakningsuppgifter eller notisuppgifter vara kvar")
def nothing_left(env):
    assert env.watcher._tasks == {}
    assert env.watcher._notify_tasks == set()
    assert env.notify_tasks and all(t.done() for t in env.notify_tasks)

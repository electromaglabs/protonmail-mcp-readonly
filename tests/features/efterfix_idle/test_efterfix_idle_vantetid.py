"""BDD: väntetiden mellan försöken när IDLE nekas eller bryts (G4I-2)."""
import asyncio
import logging

from pytest_bdd import given, parsers, scenarios, then, when

from tests.features.efterfix_idle.conftest import eventually, run, start_watcher

scenarios("efterfix_idle_vantetid.feature")


@given("att Bridge nekar IDLE")
def idle_refused(env):
    env.fake.idle_mode = "no"


@given("att Bridge stänger anslutningen direkt efter att IDLE börjat")
def idle_closed(env):
    env.fake.idle_mode = "close"


@given("att Bridge nekar IDLE de två första gångerna")
def idle_refused_twice(env):
    env.fake.idle_mode = "no"
    env.refusals_left = 2


def _sleeper(env):
    env.watching_samples = []

    async def sleep(delay):
        env.delays.append(delay)
        env.watching_samples.append(env.watcher.is_watching("INBOX"))
        left = getattr(env, "refusals_left", None)
        if left is not None:
            env.refusals_left = left - 1
            if env.refusals_left <= 0:
                env.fake.idle_mode = None
        await asyncio.sleep(0)

    return sleep


@when(parsers.parse(
    "bevakningen av INBOX startas med väntetiden {initial:d} sekund och taket {cap:d} sekunder"
))
def start_with_backoff(env, caplog, initial, cap):
    caplog.set_level(logging.DEBUG, logger="protonmail_mcp.imap_idle")
    env.caplog = caplog
    start_watcher(env, backoff_initial=float(initial), backoff_max=float(cap), sleep=_sleeper(env))


@when(parsers.parse(
    "bevakningen av INBOX startas med väntetiden {initial:d} sekund, taket {cap:d} sekunder "
    "och förnyelse var {renew:f} sekund"
))
def start_with_backoff_and_renewal(env, initial, cap, renew):
    start_watcher(env, backoff_initial=float(initial), backoff_max=float(cap), renew_seconds=renew,
                  sleep=_sleeper(env))


@when("en IDLE-omgång har gått klart")
def idle_round_done(env):
    eventually(env, lambda: env.watcher.is_watching("INBOX") and env.fake.idle_count() >= 4,
               what="en hel IDLE-omgång")


@when("Bridge startas om")
def restart(env):
    before = len(env.delays)
    run(env, env.fake.drop_all())
    eventually(env, lambda: len(env.delays) > before, what="nästa försök")


@then(parsers.parse("ska väntetiderna mellan försöken börja med {delays} sekunder"))
def backoff(env, delays):
    expected = [float(d) for d in delays.split(", ")]
    eventually(env, lambda: len(env.delays) >= len(expected), what="försöken")
    assert env.delays[:len(expected)] == expected


@then("ska bevakningen aldrig ha sagt att INBOX bevakas")
def never_watching(env):
    assert env.watching_samples and not any(env.watching_samples)
    assert not env.watcher.is_watching("INBOX")


@then("ska felet bara ha loggats som varning en gång")
def warned_once(env):
    warnings = [r for r in env.caplog.records
                if r.levelno == logging.WARNING and "Bevakningen av INBOX avbröts" in r.getMessage()]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]

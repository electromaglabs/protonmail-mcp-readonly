"""BDD: mejl som kommer under bevakningens sökning, hämtning eller förnyelse (G4I-1)."""
from pytest_bdd import scenarios, when

scenarios("efterfix_idle_kapplopning.feature")


def _deliver_during(env, command):
    def second():
        env.fake.deliver("INBOX", subject="Under " + command)

    env.fake.during(command, second)
    env.fake.deliver("INBOX", subject="Först")


@when("ett mejl kommer till INBOX och ett till kommer medan bevakningen hämtar det första")
def during_fetch(env):
    _deliver_during(env, "UID FETCH")


@when("ett mejl kommer till INBOX och ett till kommer medan bevakningen söker efter det första")
def during_search(env):
    _deliver_during(env, "UID SEARCH")


@when("ett mejl kommer till INBOX precis när IDLE förnyas")
def at_renewal(env):
    env.fake.during("DONE", lambda: env.fake.deliver("INBOX", subject="Vid förnyelsen"))

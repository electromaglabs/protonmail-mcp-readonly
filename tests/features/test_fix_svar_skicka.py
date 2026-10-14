"""BDD-steg för fix_svar_skicka.feature (SMTP-klienten bygger och skickar)."""
import asyncio

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.fix_svar_support import capture_smtp, header_addresses, make_client

scenarios("fix_svar_skicka.feature")


@pytest.fixture
def captured():
    with capture_smtp() as c:
        yield c


@pytest.fixture
def outcome():
    return {}


@given(parsers.parse('en SMTP-klient för kontot "{account}"'), target_fixture="client")
def smtp_client(account):
    return make_client(account)


def _send(client, outcome, **kwargs):
    kwargs.setdefault("subject", "Hej")
    kwargs.setdefault("body", "Hejsan")
    try:
        outcome["result"] = asyncio.run(client.send_email(**kwargs))
    except Exception as exc:  # noqa: BLE001 — scenariot granskar felet
        outcome["error"] = exc


@when(parsers.parse('jag skickar ett mail till "{to}"'))
def send_to(client, captured, outcome, to):
    _send(client, outcome, to=to)


@when(
    parsers.parse(
        'jag skickar ett mail till "{to}" med kopia till "{cc}" och svarsadress "{reply_to}"'
    )
)
def send_to_cc_reply_to(client, captured, outcome, to, cc, reply_to):
    _send(client, outcome, to=to, cc=cc, reply_to=reply_to)


@then(
    parsers.re(
        r'ska headern "(?P<name>[^"]+)" innehålla "(?P<display>[^"]*)" '
        r'med adressen "(?P<addr>[^"]+)"'
    )
)
def header_contains(captured, name, display, addr):
    assert (display, addr) in header_addresses(captured.parsed, name)


@then(parsers.parse('SMTP-mottagarna ska vara "{recipients}"'))
def smtp_recipients(captured, recipients):
    assert captured.recipients == [r.strip() for r in recipients.split(",")]

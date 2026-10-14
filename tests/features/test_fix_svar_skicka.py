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


@when(parsers.re(r'jag skickar ett mail till "(?P<to>[^"]+)"'))
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


@when(parsers.parse('jag skickar ett mail utan mottagare men med hemlig kopia till "{bcc}"'))
def send_bcc_only(client, captured, outcome, bcc):
    _send(client, outcome, to=[], bcc=bcc)


@then(parsers.parse('ska mejlet sakna headern "{name}"'))
def header_missing(captured, name):
    assert name not in captured.parsed


@then(parsers.parse('ska Message-ID sluta med "{suffix}"'))
def message_id_suffix(captured, suffix):
    assert str(captured.parsed["Message-ID"]).endswith(suffix)


@when(parsers.parse('jag skickar ett mail till "{to}" med ett ämne på {length:d} tecken'))
def send_long_subject(client, captured, outcome, to, length):
    outcome["subject"] = ("Långt ämne " * (length // 11 + 1))[:length]
    _send(client, outcome, to=to, subject=outcome["subject"])


@when(parsers.parse('jag skickar ett mail till "{to}" med ämnet "{subject}"'))
def send_with_subject(client, captured, outcome, to, subject):
    _send(client, outcome, to=to, subject=subject.replace("\\n", "\n"))


@then("ska mejlet ha skickats")
def was_sent(captured, outcome):
    assert "error" not in outcome, outcome.get("error")
    assert outcome["result"] is True
    assert len(captured.sent) == 1


@then("ska ämnet vara oförändrat efter överföringen")
def subject_round_trips(captured, outcome):
    assert str(captured.parsed["Subject"]) == outcome["subject"]


@then("ska ingen headerrad vara längre än 998 tecken")
def header_lines_short(captured):
    head = captured.raw.split(b"\r\n\r\n", 1)[0]
    assert max(len(line) for line in head.split(b"\r\n")) <= 998


@then(parsers.parse('ska sändningen avvisas med ett fel som nämner "{text}"'))
def rejected_with(outcome, text):
    assert text in str(outcome.get("error"))


@then("inget mejl ska ha skickats")
def nothing_sent(captured):
    assert captured.sent == []


@given(parsers.parse('att servern vägrar mottagaren "{addr}" med {code:d} "{text}"'))
def server_refuses(captured, addr, code, text):
    captured.refused[addr] = (code, text)


@when(parsers.parse('jag skickar ett mail till "{first}" och "{second}"'))
def send_to_two(client, captured, outcome, first, second):
    _send(client, outcome, to=[first, second])


@then(parsers.parse('ska felet nämna "{text}"'))
def error_mentions(outcome, text):
    assert "error" in outcome, "inget fel kastades"
    assert text in str(outcome["error"])


@then(parsers.parse('ska felet tala om att mejlet gick fram till "{addr}"'))
def error_lists_delivered(outcome, addr):
    err = outcome["error"]
    assert err.delivered == [addr]
    assert addr in str(err)

"""BDD: aioimaplib får inte ta bort "* " mitt i en LIST-rad (K2).

Kör den riktiga aioimaplib mot fejk-Bridgen över TCP
(tests/fix_imapkarna_fakeimap.py), eftersom felet sitter i bibliotekets
tolkning av svarsraden.
"""
import asyncio
from types import SimpleNamespace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import IMAPClient
from tests.fix_imapkarna_fakeimap import FakeBridge

scenarios("efterfix_imap_stjarna_i_namn.feature")


@pytest.fixture
def tcp():
    loop = asyncio.new_event_loop()
    fake = FakeBridge()
    loop.run_until_complete(fake.start())
    settings = Settings(username="u@example.com", password="pw", imap_port=fake.port, _env_file=None)
    env = SimpleNamespace(loop=loop, fake=fake, client=IMAPClient(settings), errors=[])
    env.run = lambda coro: loop.run_until_complete(asyncio.wait_for(coro, 5))
    yield env
    loop.run_until_complete(env.client.disconnect())
    loop.run_until_complete(fake.stop())
    loop.close()


@given(parsers.parse('en riktig anslutning till en Bridge med mapparna "{a}", "{b}" och "{c}"'))
def bridge_with(tcp, a, b, c):
    for name in (a, b, c):
        tcp.fake.add_mailbox(name, ["Ett brev"])


@when("jag listar mapparna över anslutningen", target_fixture="names")
def list_folders(tcp):
    return [m["name"] for m in tcp.run(tcp.client.list_mailboxes())]


@when("jag listar mejlen i varje listad mapp över anslutningen")
def list_each(tcp):
    for m in tcp.run(tcp.client.list_mailboxes()):
        try:
            tcp.run(tcp.client.list_messages(m["name"]))
        except ValueError as e:
            tcp.errors.append(str(e))


@then(parsers.parse('ska mapparna "{a}", "{b}" och "{c}" listas'))
def listed(names, a, b, c):
    assert sorted(names) == sorted([a, b, c])


@then(parsers.parse('ska ingen mapp heta "{name}"'))
def not_listed(names, name):
    assert name not in names


@then("ska varje mapp gå att öppna")
def all_open(tcp):
    assert tcp.errors == []

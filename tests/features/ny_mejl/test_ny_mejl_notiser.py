"""BDD: bevakningens nya mejl blir resursnotiser till prenumeranter (ny-mejl).

Den riktiga servern med sin riktiga lifespan (bevakning mot låtsas-Bridgen i
tests/ny_mejl_fakeidle.py) och ett MCP-klientpass i minnet.
"""
import asyncio
import time

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import config
from protonmail_mcp.config import Settings
from protonmail_mcp.server import mcp, register_tools
from tests import sdk_support as sdk
from tests.ny_mejl_fakeidle import FakeIdleBridge

scenarios("ny_mejl_notiser.feature")


@pytest.fixture
def state(monkeypatch, tmp_path):
    return {"monkeypatch": monkeypatch, "tmp": tmp_path, "mailboxes": "INBOX", "subscribe": None,
            "deliver_to": None, "notes": []}


@given("en Bridge med IDLE där INBOX har mejlen 1, 2 och 3")
def bridge(state):
    state["boxes"] = {"INBOX": [1, 2, 3], "Folders/Kunder": [7]}


@given(parsers.parse('en klient som är ansluten till servern och prenumererar på "{uri}"'))
def subscribed(state, uri):
    state["subscribe"] = uri


@given(parsers.parse('att servern även bevakar "{mailbox}"'))
def also_watch(state, mailbox):
    state["mailboxes"] += f",{mailbox}"


@when("ett mejl kommer till INBOX")
def mail_to_inbox(state):
    _run(state, "INBOX")


@when(parsers.parse('ett mejl kommer till "{mailbox}"'))
def mail_to(state, mailbox):
    _run(state, mailbox)


def _run(state, mailbox):
    register_tools()
    settings = Settings(username="u", password="p", imap_timeout=2, attachment_dir=state["tmp"] / "b",
                        watch_mailboxes=state["mailboxes"], _env_file=None)

    async def handler(message):
        uri = sdk.resource_updated_uri(message)
        if uri is not None:
            state["notes"].append(uri)

    async def scenario():
        fake = FakeIdleBridge()
        for name, uids in state["boxes"].items():
            fake.add_box(name, uids)
        port = await fake.start()
        state["monkeypatch"].setattr(config, "get_settings",
                                     lambda: settings.model_copy(update={"imap_port": port}))
        try:
            async with sdk.connect(mcp, message_handler=handler) as session:
                await session.subscribe_resource(state["subscribe"])
                # Vänta tills varje bevakad mapp ligger i IDLE
                watched = len(state["mailboxes"].split(","))
                deadline = time.monotonic() + 5
                while len({n for n, line in fake.commands if " IDLE" in line}) < watched:
                    assert time.monotonic() < deadline, "bevakningen kom aldrig i IDLE"
                    await asyncio.sleep(0.01)
                fake.deliver(mailbox, subject="Nytt")
                deadline = time.monotonic() + 1.5
                while not state["notes"] and time.monotonic() < deadline:
                    await asyncio.sleep(0.01)
        finally:
            await fake.stop()

    asyncio.run(scenario())


@then(parsers.parse('ska klienten få notisen resources/updated för "{uri}"'))
def got_note(state, uri):
    assert state["notes"] == [uri]


@then("ska klienten inte få någon notis")
def no_note(state):
    assert state["notes"] == []

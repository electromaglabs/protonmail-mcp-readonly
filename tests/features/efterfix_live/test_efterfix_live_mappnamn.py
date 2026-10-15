"""BDD: create_folder med upptaget namn ger ett begripligt svenskt fel (L5)."""
import asyncio
from unittest.mock import MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.folders import create_folder
from tests.fix_flytta_bridge import make_client

scenarios("efterfix_live_mappnamn.feature")


@pytest.fixture
def mapp(monkeypatch):
    imap, fake = make_client(monkeypatch)
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = imap
    return {"ctx": ctx, "bridge": fake, "errors": []}


@given(parsers.parse('att etiketten "{name}" finns'))
def label_exists(mapp, name):
    mapp["bridge"].add(name, "1")


@given("att Bridge nekar CREATE med Protons fel för upptaget namn")
def refuse_create(mapp):
    mapp["bridge"].refuse["CREATE"] = (
        "failed to create label: A label or folder with this name already exists (Code=2500, Status=409)"
    )


@when(parsers.parse('jag skapar "{name}"'))
def create(mapp, name):
    try:
        asyncio.run(create_folder(mapp["ctx"], name=name))
    except ValueError as exc:
        mapp["errors"].append(str(exc))


@then(parsers.parse('ska felet förklara på svenska att namnet redan används av "{other}"'))
def explained(mapp, other):
    assert mapp["errors"], "inget fel"
    text = mapp["errors"][0]
    assert other in text and "redan" in text and "unika" in text

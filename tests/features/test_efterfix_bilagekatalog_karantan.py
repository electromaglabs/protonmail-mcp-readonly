"""BDD-steg för efterfix_bilagekatalog_karantan.feature (granskning 2, S5).

Själva xattr-anropet ersätts med en attrapp; det riktiga anropet provas i
tests/unit/test_efterfix_bilagekatalog_karantan.py (bara på macOS).
"""
import logging
import time

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp import attachments as att

scenarios("efterfix_bilagekatalog_karantan.feature")


@pytest.fixture
def state():
    return {"calls": []}


@pytest.fixture(autouse=True)
def fake_xattr(state, monkeypatch):
    def fsetxattr(fd, name, value):
        state["calls"].append((fd, name, value))
        if state.get("fail"):
            raise OSError(45, "Operation not supported")

    monkeypatch.setattr(att, "_fsetxattr", fsetxattr, raising=False)


@given("att servern körs på macOS")
def on_macos(monkeypatch):
    monkeypatch.setattr(att, "_is_macos", lambda: True, raising=False)


@given("att servern körs på Linux")
def on_linux(monkeypatch):
    monkeypatch.setattr(att, "_is_macos", lambda: False, raising=False)


@given("att karantänmärkning inte går att sätta")
def xattr_fails(state):
    state["fail"] = True


@given("en tom bilagekatalog för karantän", target_fixture="root")
def empty_root(tmp_path):
    root = tmp_path / "bilagor"
    root.mkdir(mode=0o700)
    return root


@when(parsers.parse('bilagan "{name}" sparas'))
def save(root, state, name, caplog):
    caplog.set_level(logging.WARNING, logger="protonmail_mcp")
    state["before"] = int(time.time())
    state["path"] = att.AttachmentStore(root).save(name, b"<plist>CommandString</plist>")
    state["after"] = int(time.time())
    state["log"] = caplog.text


@then(parsers.parse('ska den sparade filen ha karantänmärkning från "{agent}"'))
def has_quarantine(state, agent):
    [(fd, name, value)] = state["calls"]
    assert isinstance(fd, int)
    assert name == b"com.apple.quarantine"
    assert value.decode("ascii").split(";")[2] == agent


@then(parsers.parse('ska märkningen ha flaggorna "{flags}" och aktuell tid'))
def flags_and_time(state, flags):
    [(_, _, value)] = state["calls"]
    got_flags, hex_time, _, rest = value.decode("ascii").split(";")
    assert got_flags == flags
    assert rest == ""
    assert state["before"] <= int(hex_time, 16) <= state["after"]


@then("ska bilagan ha sparats")
def saved(state):
    assert state["path"].read_bytes() == b"<plist>CommandString</plist>"


@then("ska ingen karantänmärkning ha försökts")
def not_attempted(state):
    assert state["calls"] == []


@then("ska loggen varna för att karantänmärkningen misslyckades")
def warned(state):
    assert "karantän" in state["log"]

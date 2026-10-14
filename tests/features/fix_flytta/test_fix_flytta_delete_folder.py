"""BDD: delete_folder vägrar ta bort en mapp som inte är tom, utom med force."""
from pytest_bdd import given, parsers, scenarios, when

from protonmail_mcp.tools.folders import delete_folder

from .conftest import run_tool

scenarios("fix_flytta_delete_folder.feature")


@given(parsers.parse('att mappen "{name}" finns och är tom'))
def empty_folder(bridge, name):
    bridge.mailboxes[name] = set()


@when(parsers.parse('jag tar bort mappen "{name}"'))
def delete(mock_ctx, bridge, name):
    run_tool(bridge, delete_folder(mock_ctx, name=name))


@when(parsers.parse('jag tar bort mappen "{name}" med force'))
def delete_force(mock_ctx, bridge, name):
    run_tool(bridge, delete_folder(mock_ctx, name=name, force=True))

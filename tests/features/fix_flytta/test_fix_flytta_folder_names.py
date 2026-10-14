"""BDD: create_folder/rename_folder kräver Folders/ eller Labels/ och förklarar varför."""
from pytest_bdd import parsers, scenarios, when

from protonmail_mcp.tools.folders import create_folder, rename_folder

from .conftest import run_tool

scenarios("fix_flytta_folder_names.feature")


@when(parsers.parse('jag skapar mappen "{name}"'))
def create(mock_ctx, bridge, name):
    run_tool(bridge, create_folder(mock_ctx, name=name))


@when(parsers.parse('jag byter namn på "{old}" till "{new}"'))
def rename(mock_ctx, bridge, old, new):
    run_tool(bridge, rename_folder(mock_ctx, old_name=old, new_name=new))

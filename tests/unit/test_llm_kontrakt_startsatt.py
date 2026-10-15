"""Enhetstester: python -m protonmail_mcp.server registrerar alla verktyg (llm-kontrakt)."""
import runpy
import warnings

from protonmail_mcp import server
from tests import sdk_support as sdk


def _run_as_module(monkeypatch) -> sdk.MCPServer:
    captured = sdk.patch_run(monkeypatch)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("protonmail_mcp.server", run_name="__main__")
    return captured["server"]


def test_module_start_runs_the_server_the_tools_are_registered_on(monkeypatch):
    started = _run_as_module(monkeypatch)
    assert started is server.mcp


def test_module_start_has_tools(monkeypatch):
    started = _run_as_module(monkeypatch)
    assert len(sdk.list_tools(started)) == 29


def test_register_tools_is_idempotent():
    server.register_tools()
    before = len(sdk.list_tools(server.mcp))
    server.register_tools()
    assert len(sdk.list_tools(server.mcp)) == before == 29

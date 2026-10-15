"""Enhetstester: python -m protonmail_mcp.server registrerar alla verktyg (llm-kontrakt)."""
import runpy
import warnings

from mcp.server.fastmcp import FastMCP

from protonmail_mcp import server


def _run_as_module(monkeypatch) -> FastMCP:
    captured = {}
    monkeypatch.setattr(FastMCP, "run", lambda self, *a, **k: captured.setdefault("server", self))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("protonmail_mcp.server", run_name="__main__")
    return captured["server"]


def test_module_start_runs_the_server_the_tools_are_registered_on(monkeypatch):
    started = _run_as_module(monkeypatch)
    assert started is server.mcp


def test_module_start_has_tools(monkeypatch):
    started = _run_as_module(monkeypatch)
    assert len(started._tool_manager.list_tools()) == 29


def test_register_tools_is_idempotent():
    server.register_tools()
    before = len(server.mcp._tool_manager.list_tools())
    server.register_tools()
    assert len(server.mcp._tool_manager.list_tools()) == before == 29

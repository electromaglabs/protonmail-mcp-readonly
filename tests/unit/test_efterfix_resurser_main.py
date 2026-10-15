"""python -m protonmail_mcp: paketet har en __main__ som startar samma server (efterfix-resurser)."""
import importlib.util
import runpy
import warnings

from mcp.server.fastmcp import FastMCP

from protonmail_mcp import server


def test_paketet_har_en_main_modul():
    assert importlib.util.find_spec("protonmail_mcp.__main__") is not None


def test_main_modulen_kor_server_main_och_startar_stdio(monkeypatch):
    calls = []
    monkeypatch.setattr(FastMCP, "run", lambda self, *a, **k: calls.append((self, a, k)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("protonmail_mcp", run_name="__main__", alter_sys=True)
    assert len(calls) == 1
    srv, args, kwargs = calls[0]
    assert srv is server.mcp
    assert kwargs.get("transport", args[0] if args else None) == "stdio"


def test_import_av_main_modulen_startar_ingenting(monkeypatch):
    calls = []
    monkeypatch.setattr(FastMCP, "run", lambda self, *a, **k: calls.append(self))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("protonmail_mcp.__main__", run_name="protonmail_mcp.__main__")
    assert calls == []

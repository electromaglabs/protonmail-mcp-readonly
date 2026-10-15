"""En ny installation (t.ex. `uv tool install`) läser inte uv.lock utan löser
beroendena från pyproject.toml. Servern är skriven för mcp 2.x (MCPServer):
1.x saknar mcp.server.mcpserver, och en framtida 3.x kan ändra API:erna igen,
så en installation utan gränser åt båda hållen startar kanske inte alls."""
import tomllib
from pathlib import Path

from packaging.requirements import Requirement


def _requirement(name: str) -> Requirement:
    data = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())
    for dep in data["project"]["dependencies"]:
        req = Requirement(dep)
        if req.name == name:
            return req
    raise AssertionError(f"{name} saknas i dependencies")


def test_mcp_is_2_3_or_newer_and_below_3():
    spec = _requirement("mcp").specifier
    assert spec.contains("2.3.0")
    assert not spec.contains("1.28.1"), "mcp 1.x saknar MCPServer"
    assert not spec.contains("2.2.0"), "mcp måste vara minst 2.3"
    assert not spec.contains("3.0.0"), "mcp måste ha en övre gräns <3"

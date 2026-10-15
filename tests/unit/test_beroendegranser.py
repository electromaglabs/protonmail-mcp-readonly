"""En ny installation (t.ex. `uv tool install`) läser inte uv.lock utan löser
beroendena från pyproject.toml. mcp 2.x döpte om FastMCP och ändrade API:er
som servern använder, så en installation utan övre gräns startar inte alls."""
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


def test_mcp_is_capped_below_2():
    spec = _requirement("mcp").specifier
    assert not spec.contains("2.0.0"), "mcp måste ha en övre gräns <2"
    assert spec.contains("1.28.1")

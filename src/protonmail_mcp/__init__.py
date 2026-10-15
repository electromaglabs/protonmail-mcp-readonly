"""protonmail-mcp: MCP-server för Proton Mail via ProtonMail Bridge.

Versionen har en enda källa, ``version`` i pyproject.toml; här läses den ur
det installerade paketets metadata. Servern anger samma version i serverInfo.
"""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("protonmail-mcp")
except PackageNotFoundError:  # körs från källkoden utan att paketet är installerat
    __version__ = "0+unknown"

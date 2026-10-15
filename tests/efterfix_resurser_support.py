"""Hjälp för efterfix-resurser-testerna: klientsessioner som samlar resursnotiser.

Bygger på tests/mcp_resurser_support.client_session (riktigt MCP-klientpass i
minnet, attrapper i stället för Bridge).
"""
from tests import sdk_support as sdk
from tests.mcp_resurser_support import client_session  # noqa: F401 — återexporteras


class Collector:
    """Meddelandehanterare som samlar URI:erna i notifications/resources/updated."""

    def __init__(self):
        self.uris: list[str] = []

    async def __call__(self, message):
        uri = sdk.resource_updated_uri(message)
        if uri is not None:
            self.uris.append(uri)

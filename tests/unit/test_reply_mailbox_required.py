"""reply_to_email och forward_email skickar till riktiga mottagare utifrån ett
UID. UID:n gäller per mapp, så mappen måste anges — en INBOX-default skulle
låta ett UID från Starred eller en etikett svara på ett helt annat mejl."""
import pytest

from protonmail_mcp.server import mcp
from protonmail_mcp.tools import reply  # noqa: F401  (registrerar verktygen)
from tests import sdk_support as sdk


@pytest.mark.parametrize("tool_name", ["reply_to_email", "forward_email"])
async def test_mailbox_is_required(tool_name):
    tools = {t.name: t for t in await mcp.list_tools()}
    schema = sdk.wire(tools[tool_name])["inputSchema"]
    assert "mailbox" in schema["required"]
    assert "default" not in schema["properties"]["mailbox"]

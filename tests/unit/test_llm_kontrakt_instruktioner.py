"""Enhetstester: serverinstruktionerna (llm-kontrakt)."""
from protonmail_mcp.server import INSTRUCTIONS, mcp
from tests.llm_kontrakt_support import client_session


def test_server_has_instructions():
    assert mcp.instructions == INSTRUCTIONS


def test_instructions_are_short():
    # Skickas i varje session: en arbetsbeskrivning, inte en manual
    assert len(INSTRUCTIONS) < 2000


def test_instructions_mention_drafts_before_sending():
    for tool in ("create_draft", "create_reply_draft", "create_forward_draft", "send_email", "send_draft"):
        assert tool in INSTRUCTIONS


async def test_initialize_result_carries_instructions(monkeypatch):
    async with client_session(monkeypatch) as session:
        # initialize är redan gjord; svaret ligger kvar i sessionen
        result = await session.initialize()
        assert result.instructions == INSTRUCTIONS

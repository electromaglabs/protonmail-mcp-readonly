"""BDD-steg för llm_skick_skicklage.feature (gemensamma steg i conftest.py)."""
from unittest.mock import AsyncMock

from pytest_bdd import given, parsers, scenarios, then

scenarios("llm_skick_skicklage.feature")


@given(parsers.parse('Bridge sparar utkast i Drafts med UID "{uid}"'))
def bridge_saves_drafts(state, monkeypatch, uid):
    from protonmail_mcp import imap_drafts

    saved = []

    async def store(imap, message, message_id):
        saved.append(message)
        return uid

    async def ensure_connected():
        return None

    monkeypatch.setattr(imap_drafts, "_store_draft", store)
    state["saved_drafts"] = saved

    def setup(app):
        app.imap._ensure_connected = AsyncMock(side_effect=ensure_connected)
    state["app_setup"].append(setup)


@then(parsers.parse('ska felet hänvisa till "{a}", "{b}" och "{c}"'))
def error_mentions(state, a, b, c):
    text = str(state["error"])
    for name in (a, b, c):
        assert name in text


@then("ska utkastet ha sparats i Drafts")
def draft_saved(state):
    assert len(state["saved_drafts"]) == 1


@then("ska anropet inte ha vägrats av skickläget")
def not_refused_by_send_mode(state):
    assert "PROTONMAIL_SEND_MODE" not in str(state["error"] or "")

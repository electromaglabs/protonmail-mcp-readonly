"""L5: create_folder med ett namn som redan används av en mapp eller etikett.

Live gav Bridge ett rått API-fel (409, Code=2500): Proton kräver att namnen är
unika över mappar och etiketter tillsammans.
"""
from unittest.mock import MagicMock

import pytest

from protonmail_mcp.tools.folders import create_folder
from tests.fix_flytta_bridge import make_client

CONFLICT = "failed to create label: A label or folder with this name already exists (Code=2500, Status=409)"


@pytest.fixture
def ctx_and_bridge(monkeypatch):
    imap, bridge = make_client(monkeypatch)
    ctx = MagicMock()
    ctx.request_context.lifespan_context.imap = imap
    return ctx, bridge


class TestDuplicateName:
    async def test_folder_name_taken_by_label(self, ctx_and_bridge):
        ctx, bridge = ctx_and_bridge
        bridge.add("Labels/Kvitton", "1")
        bridge.refuse["CREATE"] = CONFLICT
        with pytest.raises(ValueError) as exc:
            await create_folder(ctx, name="Folders/Kvitton")
        text = str(exc.value)
        assert "Labels/Kvitton" in text
        assert "unika" in text and "mappar och etiketter" in text
        assert "Code=2500" not in text.split("(Bridge:")[0]

    async def test_label_name_taken_by_folder_other_case(self, ctx_and_bridge):
        ctx, bridge = ctx_and_bridge
        bridge.add("Folders/Projekt/Kvitton", "1")
        bridge.refuse["CREATE"] = CONFLICT
        with pytest.raises(ValueError, match="Folders/Projekt/Kvitton"):
            await create_folder(ctx, name="Labels/kvitton")

    async def test_conflict_without_visible_twin_still_explained(self, ctx_and_bridge):
        ctx, bridge = ctx_and_bridge
        bridge.refuse["CREATE"] = CONFLICT
        with pytest.raises(ValueError, match="unika"):
            await create_folder(ctx, name="Labels/Ny")

    async def test_other_refusal_is_unchanged(self, ctx_and_bridge):
        ctx, bridge = ctx_and_bridge
        bridge.refuse["CREATE"] = "something else"
        with pytest.raises(ValueError, match="something else") as exc:
            await create_folder(ctx, name="Labels/Ny")
        assert "unika" not in str(exc.value)

    async def test_success_unchanged(self, ctx_and_bridge):
        ctx, bridge = ctx_and_bridge
        assert await create_folder(ctx, name="Labels/Ny") is True

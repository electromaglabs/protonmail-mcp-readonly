"""Starred som mål för UID MOVE avvisas (S2).

Bridge räknar Starred (etikett 10) som systemetikett, så shouldExpungeOldLocation
blir sann och mejlet tas bort ur källmappen (connector.go:640/679).
"""
import pytest

from protonmail_mcp.imap_client import _check_move
from tests.fix_flytta_bridge import make_client


@pytest.mark.parametrize("target", ["Starred", "starred", "STARRED"])
def test_starred_target_rejected(target):
    with pytest.raises(ValueError, match=r"Starred.*\\Flagged"):
        _check_move("INBOX", target)


def test_starred_source_still_allowed():
    _check_move("Starred", "Archive")


async def test_move_to_starred_sends_nothing(monkeypatch):
    imap, bridge = make_client(monkeypatch)
    bridge.add("INBOX", "3")
    with pytest.raises(ValueError, match="Flagged"):
        await imap.move_message("INBOX", "3", "Starred")
    assert bridge.commands == []

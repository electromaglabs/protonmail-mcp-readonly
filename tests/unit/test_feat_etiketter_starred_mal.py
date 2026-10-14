"""_check_move: felet för Starred som mål hänvisar till flag_email nu när verktyget finns."""
import pytest

from protonmail_mcp.imap_client import _check_move


@pytest.mark.parametrize("target", ["Starred", "starred"])
def test_starred_target_points_to_flag_email(target):
    with pytest.raises(ValueError, match="flag_email") as exc:
        _check_move("INBOX", target)
    assert "nästa fas" not in str(exc.value)

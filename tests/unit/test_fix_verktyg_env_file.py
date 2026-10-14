"""Enhetstester: config.py läser projektrotens .env, och CWD:s .env har företräde (punkt 15)."""
from pathlib import Path

from protonmail_mcp.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestEnvFileLocation:
    def test_project_root_env_is_read_with_absolute_path(self):
        env_files = [Path(p) for p in Settings.model_config["env_file"]]
        assert REPO_ROOT / ".env" in env_files
        assert all(p.is_absolute() for p in env_files if p != Path(".env"))

    def test_cwd_env_is_read_last_so_it_wins(self):
        env_files = [Path(p) for p in Settings.model_config["env_file"]]
        assert env_files[-1] == Path(".env")

"""Enhetstester: bilagekatalogens skydd ska inte bero på filsystem eller användare.

På ext4/overlayfs (GitHub Actions, Docker) får en ny fil ofta samma inodnummer
som en nyss borttagen. Att bara jämföra (st_dev, st_ino) räcker då inte för att
upptäcka att filen bytts ut mellan kontroll och läsning.
"""
import os

import pytest

from protonmail_mcp.attachments import AttachmentStore, load_for_sending

_INT_FIELDS = ("st_mode", "st_ino", "st_dev", "st_nlink", "st_uid", "st_gid", "st_size")


def stat_replace(st: os.stat_result, **changes) -> os.stat_result:
    """Kopia av ett stat-resultat med ändrade fält (även st_*_ns)."""
    _, (seq, extra) = st.__reduce__()
    seq, extra = list(seq), dict(extra)
    for name, value in changes.items():
        if name in _INT_FIELDS:
            seq[_INT_FIELDS.index(name)] = value
        else:
            extra[name] = value
    return os.stat_result(seq, extra)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "bilagor"
    root.mkdir(mode=0o700)
    return root


def _swap_after_check(store, monkeypatch, path, new_content, adjust=lambda checked, new: {}):
    """Byt filen efter kontrollen mot en ny fil som (som på ext4) får samma
    inodnummer. ``adjust`` kan ändra fler fält i det kontrollerade stat-resultatet."""
    checked = store._checked_file

    def swap(name):
        result = checked(name)
        path.unlink()
        path.write_bytes(new_content)
        new = os.lstat(path)
        changes = {"st_ino": new.st_ino, "st_dev": new.st_dev, **adjust(result.stat, new)}
        return result._replace(stat=stat_replace(result.stat, **changes))

    monkeypatch.setattr(store, "_checked_file", swap)


class TestInodeReuse:
    def test_new_file_with_reused_inode_and_other_size_is_not_sent(self, root, monkeypatch):
        (root / "a.txt").write_bytes(b"ofarlig")
        store = AttachmentStore(root)
        _swap_after_check(store, monkeypatch, root / "a.txt", b"ny fil med annat innehall")
        with pytest.raises(ValueError, match="ändrades"):
            load_for_sending(["a.txt"], store)

    def test_new_file_with_reused_inode_same_size_and_mtime_is_not_sent(
        self, root, monkeypatch
    ):
        # Samma storlek och mtime (som kan sättas med utime) — bara ctime, som
        # användaren inte kan sätta, skiljer
        (root / "a.txt").write_bytes(b"ofarlig")
        store = AttachmentStore(root)
        _swap_after_check(
            store, monkeypatch, root / "a.txt", b"FARLIG!",
            lambda old, new: {
                "st_size": new.st_size,
                "st_mtime_ns": new.st_mtime_ns,
                "st_ctime_ns": new.st_ctime_ns - 1,
            },
        )
        with pytest.raises(ValueError, match="ändrades"):
            load_for_sending(["a.txt"], store)

    def test_new_file_with_reused_inode_same_size_and_ctime_but_other_mtime_is_not_sent(
        self, root, monkeypatch
    ):
        (root / "a.txt").write_bytes(b"ofarlig")
        store = AttachmentStore(root)
        _swap_after_check(
            store, monkeypatch, root / "a.txt", b"FARLIG!",
            lambda old, new: {
                "st_size": new.st_size,
                "st_mtime_ns": new.st_mtime_ns - 1,
                "st_ctime_ns": new.st_ctime_ns,
            },
        )
        with pytest.raises(ValueError, match="ändrades"):
            load_for_sending(["a.txt"], store)

    def test_unchanged_file_is_still_sent(self, root):
        (root / "a.txt").write_bytes(b"ofarlig")
        [part] = load_for_sending(["a.txt"], AttachmentStore(root))
        assert part.get_filename() == "a.txt"
        assert part.get_content() == "ofarlig"

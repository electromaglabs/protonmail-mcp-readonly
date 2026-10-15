"""Enhetstester: bilagekatalogens skydd ska inte bero på filsystem eller användare.

På ext4/overlayfs (GitHub Actions, Docker) får en ny fil ofta samma inodnummer
som en nyss borttagen. Att bara jämföra (st_dev, st_ino) räcker då inte för att
upptäcka att filen bytts ut mellan kontroll och läsning.

I en container körs testerna ofta som root, och då ägs alla symlänkar av root —
"ägd av root" skiljer inte längre systemets egna symlänkar från en uppackad zips.
"""
import os
from pathlib import Path

import pytest

from protonmail_mcp import attachments as att
from protonmail_mcp.attachments import AttachmentStore, load_for_sending

# Som root godtas ingen symlänk alls (se test_..._when_running_as_root), så
# testerna av att systemets symlänkar fortfarande fungerar gäller bara andra.
not_root = pytest.mark.skipif(
    hasattr(os, "getuid") and os.getuid() == 0,
    reason="som root godtas inga symlänker på vägen till bilagekatalogen",
)

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


class TestRootOwnedSymlinks:
    """Symlänkar på vägen till bilagekatalogen godtas bara om de är systemets
    egna: ägda av root, i en katalog som bara root eller du kan ändra, och
    bara när processen inte själv är root (då ägs alla symlänkar den skapar,
    eller som en uppackad zip skapar, av root)."""

    @pytest.fixture
    def fake(self, monkeypatch):
        changes: dict = {}
        real_lstat = os.lstat

        def lstat(path, *a, **kw):
            st = real_lstat(path, *a, **kw)
            extra = changes.get(Path(path))
            return stat_replace(st, **extra) if extra else st

        monkeypatch.setattr(att.os, "lstat", lstat)
        return changes

    @pytest.fixture
    def via(self, tmp_path):
        (tmp_path / "real" / "bilagor").mkdir(mode=0o700, parents=True)
        (tmp_path / "real" / "bilagor" / "a.txt").write_text("x")
        (tmp_path / "dir").mkdir(mode=0o700)
        link = tmp_path / "dir" / "via"
        link.symlink_to(tmp_path / "real")
        return link

    @not_root
    def test_root_owned_symlink_in_private_directory_is_allowed(self, via, fake):
        fake[via] = {"st_uid": 0}
        store = AttachmentStore(via / "bilagor")
        assert store.resolve_existing("a.txt").name == "a.txt"

    def test_root_owned_symlink_is_rejected_when_running_as_root(
        self, via, fake, monkeypatch
    ):
        fake[via] = {"st_uid": 0}
        monkeypatch.setattr(att, "_current_uid", lambda: 0)
        with pytest.raises(ValueError, match="symlänk"):
            AttachmentStore(via / "bilagor").resolve_existing("a.txt")

    def test_root_owned_symlink_is_not_created_through_when_running_as_root(
        self, tmp_path, via, fake, monkeypatch
    ):
        fake[via] = {"st_uid": 0}
        monkeypatch.setattr(att, "_current_uid", lambda: 0)
        with pytest.raises(ValueError, match="symlänk"):
            AttachmentStore(via / "ny" / "bilagor").save("x.txt", b"1")
        assert not (tmp_path / "real" / "ny").exists()

    @pytest.mark.parametrize("mode", [0o777, 0o775, 0o757, 0o1777], ids=oct)
    def test_root_owned_symlink_in_directory_writable_by_others_is_rejected(
        self, via, fake, mode
    ):
        fake[via] = {"st_uid": 0}
        via.parent.chmod(mode)
        with pytest.raises(ValueError, match="symlänk"):
            AttachmentStore(via / "bilagor").resolve_existing("a.txt")

    def test_root_owned_symlink_in_directory_owned_by_someone_else_is_rejected(
        self, via, fake
    ):
        fake[via] = {"st_uid": 0}
        fake[via.parent] = {"st_uid": os.getuid() + 1}
        with pytest.raises(ValueError, match="symlänk"):
            AttachmentStore(via / "bilagor").resolve_existing("a.txt")

    @not_root
    def test_root_owned_symlink_in_root_owned_directory_is_allowed(self, via, fake):
        fake[via] = {"st_uid": 0}
        fake[via.parent] = {"st_uid": 0, "st_mode": 0o40755}
        store = AttachmentStore(via / "bilagor")
        assert store.resolve_existing("a.txt").name == "a.txt"

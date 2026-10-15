"""Enhetstester: bilagekatalogens rot och filerna som skickas (granskning 2, S1)."""
import logging
import os
import stat
from pathlib import Path

import pytest

from protonmail_mcp import attachments as att
from protonmail_mcp.attachments import AttachmentStore, load_for_sending
from protonmail_mcp.config import Settings

KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----\n"


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "bilagor"
    root.mkdir(mode=0o700)
    return root


class TestRoot:
    def test_symlink_root_is_rejected_for_saving(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real)
        with pytest.raises(ValueError, match="symlänk"):
            AttachmentStore(link).save("x.txt", b"1")
        assert list(real.iterdir()) == []

    def test_symlink_root_is_rejected_for_sending(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        (real / "a.txt").write_text("x")
        link = tmp_path / "link"
        link.symlink_to(real)
        with pytest.raises(ValueError, match="symlänk"):
            AttachmentStore(link).resolve_existing("a.txt")

    def test_root_below_user_symlink_is_rejected(self, tmp_path):
        (tmp_path / "real").mkdir()
        (tmp_path / "via").symlink_to(tmp_path / "real")
        (tmp_path / "real" / "bilagor").mkdir(mode=0o700)
        with pytest.raises(ValueError, match="symlänk"):
            AttachmentStore(tmp_path / "via" / "bilagor").resolve_existing("x")

    def test_root_below_missing_parent_under_symlink_is_not_created(self, tmp_path):
        (tmp_path / "real").mkdir()
        (tmp_path / "via").symlink_to(tmp_path / "real")
        with pytest.raises(ValueError, match="symlänk"):
            AttachmentStore(tmp_path / "via" / "ny" / "bilagor").save("x.txt", b"1")
        assert list((tmp_path / "real").iterdir()) == []

    @pytest.mark.skipif(
        hasattr(os, "getuid") and os.getuid() == 0,
        reason="som root godtas inga symlänker (test_ci_linux_bilagekatalog.py)",
    )
    def test_system_symlink_owned_by_root_is_allowed(self, tmp_path, monkeypatch):
        # /var -> private/var och /tmp -> private/tmp på macOS ägs av root
        (tmp_path / "real").mkdir()
        (tmp_path / "via").symlink_to(tmp_path / "real")
        real_lstat = os.lstat

        def lstat(path, *a, **kw):
            st = real_lstat(path, *a, **kw)
            if Path(path) == tmp_path / "via":
                fields = list(st)
                fields[stat.ST_UID] = 0
                return os.stat_result(fields)
            return st

        monkeypatch.setattr(att.os, "lstat", lstat)
        path = AttachmentStore(tmp_path / "via" / "bilagor").save("x.txt", b"1")
        assert path == (tmp_path / "real" / "bilagor" / "x.txt")

    @pytest.mark.parametrize("mode", [0o777, 0o770, 0o702, 0o720])
    def test_root_writable_by_others_is_rejected(self, root, mode):
        root.chmod(mode)
        with pytest.raises(ValueError, match="skrivbar"):
            AttachmentStore(root).save("x.txt", b"1")
        with pytest.raises(ValueError, match="skrivbar"):
            AttachmentStore(root).resolve_existing("x.txt")

    @pytest.mark.parametrize("mode", [0o700, 0o755, 0o750])
    def test_root_readable_by_others_is_allowed(self, root, mode):
        root.chmod(mode)
        assert AttachmentStore(root).save("x.txt", b"1").name == "x.txt"

    def test_root_owned_by_someone_else_is_rejected(self, root, monkeypatch):
        monkeypatch.setattr(att, "_current_uid", lambda: os.getuid() + 1, raising=False)
        with pytest.raises(ValueError, match="ägs inte av dig"):
            AttachmentStore(root).save("x.txt", b"1")
        with pytest.raises(ValueError, match="ägs inte av dig"):
            AttachmentStore(root).resolve_existing("x.txt")

    def test_relative_root_is_rejected(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="absolut"):
            AttachmentStore("bilagor").save("x.txt", b"1")
        assert not (tmp_path / "bilagor").exists()

    def test_root_swapped_for_symlink_after_check_is_not_written_through(
        self, tmp_path, monkeypatch
    ):
        root = tmp_path / "bilagor"
        root.mkdir(mode=0o700)
        outside = tmp_path / "utanfor"
        outside.mkdir()
        store = AttachmentStore(root)
        checked = store._checked_root

        def swap(*a, **kw):
            result = checked(*a, **kw)
            root.rename(tmp_path / "gammal")
            root.symlink_to(outside)
            return result

        monkeypatch.setattr(store, "_checked_root", swap)
        with pytest.raises(ValueError):
            store.save("x.txt", b"1")
        assert list(outside.iterdir()) == []


class TestSettings:
    def test_relative_attachment_dir_is_rejected(self):
        with pytest.raises(ValueError, match="absolut"):
            Settings(username="u@x.se", password="p", attachment_dir="bilagor", _env_file=None)

    def test_tilde_and_absolute_are_accepted(self, tmp_path):
        s = Settings(username="u@x.se", password="p", attachment_dir=tmp_path, _env_file=None)
        assert s.attachment_dir == tmp_path
        s = Settings(username="u@x.se", password="p", attachment_dir="~/x", _env_file=None)
        assert s.attachment_dir.is_absolute()


class TestPrepareAtStartup:
    def _settings(self, path):
        return Settings(username="u@x.se", password="p", attachment_dir=path, _env_file=None)

    def test_creates_missing_root_with_0700(self, tmp_path):
        root = tmp_path / "a" / "bilagor"
        att.prepare_attachment_dir(self._settings(root))
        assert root.is_dir()
        assert (root.stat().st_mode & 0o777) == 0o700

    def test_existing_root_is_left_alone(self, root):
        root.chmod(0o755)
        (root / "f.txt").write_text("x")
        att.prepare_attachment_dir(self._settings(root))
        assert (root.stat().st_mode & 0o777) == 0o755
        assert (root / "f.txt").read_text() == "x"

    def test_bad_root_only_logs_a_warning(self, tmp_path, caplog):
        link = tmp_path / "link"
        link.symlink_to(tmp_path)
        caplog.set_level(logging.WARNING)
        att.prepare_attachment_dir(self._settings(link))  # kastar inte
        assert "symlänk" in caplog.text
        assert link.is_symlink()

    def test_uncreatable_root_only_logs_a_warning(self, tmp_path, caplog):
        (tmp_path / "fil").write_text("x")
        caplog.set_level(logging.WARNING)
        att.prepare_attachment_dir(self._settings(tmp_path / "fil" / "bilagor"))
        assert "Bilagekatalogen" in caplog.text


class TestFileToSend:
    def test_hard_link_is_rejected(self, root, tmp_path):
        (tmp_path / "hemlig.txt").write_text("x")
        os.link(tmp_path / "hemlig.txt", root / "kopia.txt")
        with pytest.raises(ValueError, match="hårda länkar"):
            load_for_sending(["kopia.txt"], AttachmentStore(root))

    def test_fifo_is_rejected_without_blocking(self, root):
        os.mkfifo(root / "ror")
        with pytest.raises(ValueError, match="inte en vanlig fil"):
            load_for_sending(["ror"], AttachmentStore(root))

    def test_file_swapped_for_symlink_after_check_is_not_sent(self, root, tmp_path, monkeypatch):
        (root / "a.txt").write_text("ofarlig")
        secret = tmp_path / "hemlig.txt"
        secret.write_text("hemligt innehåll")
        store = AttachmentStore(root)
        checked = store._checked_file

        def swap(name):
            result = checked(name)
            (root / "a.txt").unlink()
            (root / "a.txt").symlink_to(secret)
            return result

        monkeypatch.setattr(store, "_checked_file", swap)
        with pytest.raises(ValueError, match="ändrades"):
            load_for_sending(["a.txt"], store)

    def test_file_replaced_by_other_file_after_check_is_not_sent(self, root, monkeypatch):
        (root / "a.txt").write_text("ofarlig")
        store = AttachmentStore(root)
        checked = store._checked_file

        def swap(name):
            result = checked(name)
            (root / "a.txt").unlink()
            (root / "a.txt").write_text("ny fil med annat innehåll")
            return result

        monkeypatch.setattr(store, "_checked_file", swap)
        with pytest.raises(ValueError, match="ändrades"):
            load_for_sending(["a.txt"], store)

    def test_directory_swapped_for_symlink_after_check_is_not_sent(
        self, root, tmp_path, monkeypatch
    ):
        (root / "sub").mkdir()
        (root / "sub" / "a.txt").write_text("ofarlig")
        outside = tmp_path / "utanfor"
        outside.mkdir()
        (outside / "a.txt").write_text("hemligt")
        store = AttachmentStore(root)
        checked = store._checked_file

        def swap(name):
            result = checked(name)
            (root / "sub").rename(root / "gammal")
            (root / "sub").symlink_to(outside)
            return result

        monkeypatch.setattr(store, "_checked_file", swap)
        with pytest.raises(ValueError, match="ändrades"):
            load_for_sending(["sub/a.txt"], store)

    def test_symlink_inside_root_to_file_inside_still_works(self, root):
        (root / "f.txt").write_text("x")
        (root / "l.txt").symlink_to(root / "f.txt")
        [part] = load_for_sending(["l.txt"], AttachmentStore(root))
        assert part.get_filename() == "f.txt"


class TestSensitiveFiles:
    @pytest.mark.parametrize(
        "name",
        [
            ".env", ".ENV", ".env.production", "app/.env", ".ssh/known_hosts",
            ".gnupg/x", ".aws/config", ".netrc", "id_rsa", "id_ecdsa_sk", "ID_ED25519",
            "id_ed25519.pub", "cert.PEM", "tls.key", "login.keychain", "login.keychain-db",
            "Keychains/x.db",
        ],
    )
    def test_sensitive_names_are_rejected(self, root, name):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x")
        with pytest.raises(ValueError, match="hemligheter"):
            load_for_sending([name], AttachmentStore(root))

    def test_sensitive_name_via_symlink_inside_root_is_rejected(self, root):
        (root / ".env").write_text("SECRET=1")
        (root / "ofarlig.txt").symlink_to(root / ".env")
        with pytest.raises(ValueError, match="hemligheter"):
            load_for_sending(["ofarlig.txt"], AttachmentStore(root))

    def test_absolute_path_to_sensitive_file_is_rejected(self, root):
        (root / ".netrc").write_text("machine x")
        with pytest.raises(ValueError, match="hemligheter"):
            load_for_sending([str(root / ".netrc")], AttachmentStore(root))

    @pytest.mark.parametrize(
        "header",
        [
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----",
            "-----BEGIN ENCRYPTED PRIVATE KEY-----",
            "-----BEGIN PGP PRIVATE KEY BLOCK-----",
        ],
    )
    def test_private_key_content_is_rejected_whatever_the_name(self, root, header):
        (root / "faktura.txt").write_text(f"text före\n{header}\nabc\n")
        with pytest.raises(ValueError, match="hemligheter"):
            load_for_sending(["faktura.txt"], AttachmentStore(root))

    @pytest.mark.parametrize(
        "name",
        ["id_kort.pdf", "identitet.txt", "environment.txt", "nyckeltal.xlsx", "env.txt",
         "certifikat.pdf", "keys.txt", "ssh-guide.pdf"],
    )
    def test_ordinary_names_are_allowed(self, root, name):
        (root / name).write_text("vanligt innehåll")
        [part] = load_for_sending([name], AttachmentStore(root))
        assert part.get_filename() == name

    def test_public_key_text_is_allowed(self, root):
        (root / "nyckel.txt").write_text("-----BEGIN PUBLIC KEY-----\nabc\n")
        [part] = load_for_sending(["nyckel.txt"], AttachmentStore(root))
        assert part.get_filename() == "nyckel.txt"

    def test_rejection_happens_before_anything_is_returned(self, root):
        (root / "ok.pdf").write_text("x")
        (root / "id_rsa").write_text(KEY)
        with pytest.raises(ValueError, match="id_rsa"):
            load_for_sending(["ok.pdf", "id_rsa"], AttachmentStore(root))

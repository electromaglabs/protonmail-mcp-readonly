"""Enhetstester för bilagekatalogen (protonmail_mcp.attachments)."""
import os
from pathlib import Path

import pytest

from protonmail_mcp.attachments import AttachmentStore, sanitize_filename
from protonmail_mcp.config import Settings
from tests.tidsmatning import assert_linear


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("faktura.pdf", "faktura.pdf"),
            ("räkning åäö.pdf", "räkning åäö.pdf"),
            ("../../etc/passwd", "passwd"),
            ("C:\\Users\\x\\evil.bat", "evil.bat"),
            ("/abs/path/fil.txt", "fil.txt"),
            ("  .dold.txt  ", "dold.txt"),
            ("namn.  ", "namn"),
            (" . .dold.txt", "dold.txt"),
            ("namn . . ", "namn"),
            ("a\x00b\x1fc\x7f.txt", "abc.txt"),
            ("rapport\u202efdp.exe", "rapportfdp.exe"),
            ("zero\u200bwidth.txt", "zerowidth.txt"),
            ('a<b>c:d"e|f?g*h.txt', "a_b_c_d_e_f_g_h.txt"),
            ("CON.txt", "_CON.txt"),
            ("e\u0301.txt", "\u00e9.txt"),  # NFC
        ],
    )
    def test_cleans(self, raw, expected):
        assert sanitize_filename(raw) == expected

    @pytest.mark.parametrize("raw", ["", "..", ".", "   ", "/", "\u202e", None])
    def test_empty_becomes_neutral_name(self, raw):
        assert sanitize_filename(raw) == "bilaga.bin"

    def test_empty_uses_content_type_extension(self):
        assert sanitize_filename("", "application/pdf") == "bilaga.pdf"
        assert sanitize_filename(None, "message/rfc822") == "bilaga.eml"

    def test_long_name_is_cut_but_keeps_extension(self):
        name = sanitize_filename("å" * 500 + ".pdf")
        assert name.endswith(".pdf")
        assert len(name.encode("utf-8")) <= 200

    def test_huge_hostile_name_is_linear(self):
        def make(n):
            return " ." * n + "x" + ". " * n + "\u202e" * (n // 200)

        assert sanitize_filename(make(200_000)) == "x"
        # n mot 4n i stället för en absolut gräns, som föll på långsamma maskiner
        assert_linear(sanitize_filename, make, 50_000)

    def test_long_extension_is_not_kept(self):
        name = sanitize_filename("x." + "y" * 300)
        assert len(name.encode("utf-8")) <= 200


class TestSave:
    def test_creates_root_with_0700(self, tmp_path):
        root = tmp_path / "a" / "b"
        AttachmentStore(root).save("x.txt", b"1")
        assert (root.stat().st_mode & 0o777) == 0o700

    def test_saved_file_is_private(self, tmp_path):
        path = AttachmentStore(tmp_path).save("x.txt", b"1")
        assert (path.stat().st_mode & 0o777) == 0o600

    def test_existing_root_permissions_are_left_alone(self, tmp_path):
        tmp_path.chmod(0o755)
        AttachmentStore(tmp_path).save("x.txt", b"1")
        assert (tmp_path.stat().st_mode & 0o777) == 0o755

    def test_collisions_get_increasing_suffix(self, tmp_path):
        store = AttachmentStore(tmp_path)
        paths = [store.save("a.pdf", bytes([i])) for i in range(3)]
        assert [p.name for p in paths] == ["a.pdf", "a (1).pdf", "a (2).pdf"]
        assert [p.read_bytes() for p in paths] == [b"\x00", b"\x01", b"\x02"]

    def test_collision_without_extension(self, tmp_path):
        store = AttachmentStore(tmp_path)
        store.save("README", b"1")
        assert store.save("README", b"2").name == "README (1)"

    def test_dangling_symlink_is_not_followed(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        target = tmp_path / "skapad-utanfor.txt"
        (root / "x.txt").symlink_to(target)
        path = AttachmentStore(root).save("x.txt", b"1")
        assert path.name == "x (1).txt"
        assert not target.exists()

    def test_root_symlink_is_rejected(self, tmp_path):
        # Granskning 2, S1: en rot som är en symlänk följs inte längre
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real)
        with pytest.raises(ValueError, match="symlänk"):
            AttachmentStore(link).save("x.txt", b"1")
        assert not (real / "x.txt").exists()

    def test_dangling_symlink_root_gives_clear_error(self, tmp_path):
        root = tmp_path / "root"
        root.symlink_to(tmp_path / "finns-inte")
        with pytest.raises(ValueError, match="Bilagekatalogen"):
            AttachmentStore(root).save("x.txt", b"1")

    def test_root_that_is_a_file_gives_clear_error(self, tmp_path):
        root = tmp_path / "fil"
        root.write_text("x")
        with pytest.raises(ValueError, match="Bilagekatalogen"):
            AttachmentStore(root).save("x.txt", b"1")


class TestResolveExisting:
    def test_nested_relative_path_inside_root(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "f.txt").write_text("x")
        assert AttachmentStore(tmp_path).resolve_existing("sub/f.txt") == tmp_path.resolve() / "sub" / "f.txt"

    def test_symlink_inside_root_is_allowed(self, tmp_path):
        (tmp_path / "f.txt").write_text("x")
        (tmp_path / "l.txt").symlink_to(tmp_path / "f.txt")
        assert AttachmentStore(tmp_path).resolve_existing("l.txt") == tmp_path.resolve() / "f.txt"

    def test_dotdot_that_stays_inside_is_allowed(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "f.txt").write_text("x")
        assert AttachmentStore(tmp_path).resolve_existing("sub/../f.txt").name == "f.txt"

    @pytest.mark.parametrize("name", ["", "  ", "a\x00b", "a\rb", "a\x7fb", "a\u202eb", "a\u2028b"])
    def test_bad_names_are_rejected(self, tmp_path, name):
        with pytest.raises(ValueError):
            AttachmentStore(tmp_path).resolve_existing(name)

    def test_root_itself_is_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            AttachmentStore(tmp_path).resolve_existing(str(tmp_path))

    def test_prefix_sibling_is_outside(self, tmp_path):
        root = tmp_path / "bilagor"
        root.mkdir()
        sibling = tmp_path / "bilagor-hemlig"
        sibling.mkdir()
        (sibling / "f.txt").write_text("x")
        with pytest.raises(ValueError, match="bilagekatalogen"):
            AttachmentStore(root).resolve_existing(str(sibling / "f.txt"))

    def test_tilde_is_not_expanded(self, tmp_path):
        with pytest.raises(ValueError, match="finns inte"):
            AttachmentStore(tmp_path).resolve_existing("~/.ssh/id_ed25519")


class TestSettings:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("PROTONMAIL_ATTACHMENT_DIR", raising=False)
        monkeypatch.delenv("PROTONMAIL_ATTACHMENT_MAX_INLINE_BYTES", raising=False)
        s = Settings(username="u@x.se", password="p", _env_file=None)
        assert s.attachment_dir == Path(os.path.expanduser("~/Downloads/protonmail-mcp"))
        assert s.attachment_max_inline_bytes == 1024 * 1024

    def test_tilde_in_env_is_expanded(self, monkeypatch):
        monkeypatch.setenv("PROTONMAIL_ATTACHMENT_DIR", "~/egna-bilagor")
        s = Settings(username="u@x.se", password="p", _env_file=None)
        assert str(s.attachment_dir) == os.path.expanduser("~/egna-bilagor")

    def test_inline_limit_must_be_positive(self):
        with pytest.raises(ValueError):
            Settings(username="u@x.se", password="p", attachment_max_inline_bytes=0, _env_file=None)

    def test_store_from_settings(self, tmp_path):
        s = Settings(
            username="u@x.se", password="p", attachment_dir=tmp_path,
            attachment_max_inline_bytes=10, _env_file=None,
        )
        store = AttachmentStore.from_settings(s)
        assert store.root == tmp_path
        assert store.max_inline_bytes == 10

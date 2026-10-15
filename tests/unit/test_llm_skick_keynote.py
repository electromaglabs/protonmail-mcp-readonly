"""Spärren för *.key släpper igenom Keynote-presentationer (zip), inget annat."""
import pytest

from protonmail_mcp.attachments import AttachmentStore, load_for_sending

ZIP = b"PK\x03\x04" + b"\x00" * 60


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "bilagor"
    path.mkdir(mode=0o700)
    return path


@pytest.mark.parametrize("name", ["Kvartal.key", "PRES.KEY", "mapp/Tal.key", "två ord.key"])
def test_zip_key_files_are_allowed(root, name):
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(ZIP)
    (part,) = load_for_sending([name], AttachmentStore(root))
    assert part.get_filename() == name.rsplit("/", 1)[-1]


def test_absolute_path_to_keynote_is_allowed(root):
    (root / "Kvartal.key").write_bytes(ZIP)
    (part,) = load_for_sending([str(root / "Kvartal.key")], AttachmentStore(root))
    assert part.get_filename() == "Kvartal.key"


@pytest.mark.parametrize(
    "name",
    ["id_rsa.key", ".env.key", "login.keychain.key", "cert.pem.key", "nycklar.key/Kvartal.key", ".ssh/Kvartal.key"],
)
def test_other_sensitive_reasons_still_refuse_zip(root, name):
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(ZIP)
    with pytest.raises(ValueError, match="hemligheter"):
        load_for_sending([name], AttachmentStore(root))


@pytest.mark.parametrize("content", [b"", b"PK", b"PK\x05\x06" + b"\x00" * 18, b"hemligt", b"-----BEGIN RSA PRIVATE KEY-----\n"])
def test_non_zip_key_files_are_refused(root, content):
    (root / "x.key").write_bytes(content)
    with pytest.raises(ValueError, match="hemligheter"):
        load_for_sending(["x.key"], AttachmentStore(root))


def test_zip_with_private_key_inside_is_refused(root):
    (root / "x.key").write_bytes(ZIP + b"-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n")
    with pytest.raises(ValueError, match="privat nyckel"):
        load_for_sending(["x.key"], AttachmentStore(root))


def test_pem_is_still_refused_even_if_zip(root):
    (root / "x.pem").write_bytes(ZIP)
    with pytest.raises(ValueError, match="hemligheter"):
        load_for_sending(["x.pem"], AttachmentStore(root))

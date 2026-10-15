"""Enhetstester: filer från bilagekatalogen blir MIME-bilagor att skicka."""
import pytest

from protonmail_mcp import attachments as att
from protonmail_mcp.attachments import AttachmentStore, load_for_sending
from protonmail_mcp.server import mcp
from protonmail_mcp.tools import reply, send  # noqa: F401 — registrerar verktygen
from tests.feat_bilagor_support import attachment_env  # noqa: F401
from tests import sdk_support as sdk


@pytest.fixture
def store(tmp_path):
    return AttachmentStore(tmp_path)


def test_none_and_empty_give_no_parts(store):
    assert load_for_sending(None, store) == []
    assert load_for_sending([], store) == []


@pytest.mark.parametrize(
    ("name", "ctype"),
    [
        ("a.pdf", "application/pdf"),
        ("a.txt", "text/plain"),
        ("a.PNG", "image/png"),
        ("a.tar.gz", "application/octet-stream"),  # komprimerad: inte application/x-tar
        ("utan_andelse", "application/octet-stream"),
    ],
)
def test_content_type_is_guessed(store, tmp_path, name, ctype):
    (tmp_path / name).write_bytes(b"data")
    [part] = load_for_sending([name], store)
    assert part.get_content_type() == ctype
    assert part.get_content_disposition() == "attachment"
    assert part.get_filename() == name
    assert part.get_payload(decode=True) == b"data"


def test_text_file_bytes_are_kept_exactly(store, tmp_path):
    data = "rad1\r\nrad2\nåäö".encode("latin-1")
    (tmp_path / "a.txt").write_bytes(data)
    [part] = load_for_sending(["a.txt"], store)
    assert part.get_payload(decode=True) == data


def test_filename_is_basename_of_resolved_path(store, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.pdf").write_bytes(b"x")
    [part] = load_for_sending(["sub/a.pdf"], store)
    assert part.get_filename() == "a.pdf"


def test_too_many_files(store, tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    assert len(load_for_sending(["a.pdf"] * att.MAX_SEND_FILES, store)) == att.MAX_SEND_FILES
    with pytest.raises(ValueError, match="högst 20"):
        load_for_sending(["a.pdf"] * (att.MAX_SEND_FILES + 1), store)


def test_total_size_limit(store, tmp_path, monkeypatch):
    monkeypatch.setattr(att, "MAX_SEND_BYTES", 10)
    (tmp_path / "a").write_bytes(b"12345")
    (tmp_path / "b").write_bytes(b"123456")
    assert len(load_for_sending(["a", "a"], store)) == 2  # exakt 10 byte går
    with pytest.raises(ValueError, match="25 MB"):
        load_for_sending(["a", "b"], store)


def test_errors_name_the_file(store):
    with pytest.raises(ValueError, match="saknas.pdf"):
        load_for_sending(["saknas.pdf"], store)


def test_default_store_comes_from_settings(attachment_env):
    root, _ = attachment_env
    root.mkdir()
    (root / "a.pdf").write_bytes(b"x")
    [part] = load_for_sending(["a.pdf"])
    assert part.get_filename() == "a.pdf"


@pytest.mark.parametrize("tool", ["send_email", "reply_to_email", "forward_email"])
def test_tools_accept_attachments(tool):
    schema = sdk.get_tool(mcp, tool).parameters
    prop = schema["properties"]["attachments"]
    assert "attachments" not in schema.get("required", [])
    array = next(s for s in prop["anyOf"] if s.get("type") == "array")
    assert array["maxItems"] == 20
    assert array["items"]["type"] == "string"

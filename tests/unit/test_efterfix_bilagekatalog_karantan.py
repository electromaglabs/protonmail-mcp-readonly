"""Enhetstester: karantänmärkning av sparade bilagor (granskning 2, S5)."""
import logging
import subprocess
import sys

import pytest

from protonmail_mcp import attachments as att
from protonmail_mcp.attachments import AttachmentStore


@pytest.fixture
def calls(monkeypatch):
    calls = []
    monkeypatch.setattr(att, "_fsetxattr", lambda fd, n, v: calls.append((fd, n, v)), raising=False)
    return calls


def test_value_format():
    value = att._quarantine_value(0x6A0B1C2D)
    assert value == b"0083;6a0b1c2d;protonmail-mcp;"


def test_is_macos_follows_platform(monkeypatch):
    monkeypatch.setattr(att.sys, "platform", "darwin")
    assert att._is_macos() is True
    monkeypatch.setattr(att.sys, "platform", "linux")
    assert att._is_macos() is False


def test_marked_while_file_is_open(tmp_path, monkeypatch, calls):
    monkeypatch.setattr(att, "_is_macos", lambda: True)
    path = AttachmentStore(tmp_path).save("a.zip", b"PK")
    [(fd, name, value)] = calls
    assert name == b"com.apple.quarantine"
    assert value.startswith(b"0083;")
    assert path.read_bytes() == b"PK"


def test_no_call_off_macos(tmp_path, monkeypatch, calls):
    monkeypatch.setattr(att, "_is_macos", lambda: False)
    AttachmentStore(tmp_path).save("a.zip", b"PK")
    assert calls == []


@pytest.mark.parametrize("exc", [OSError(1, "Operation not permitted"), AttributeError("fsetxattr")])
def test_failure_is_logged_not_raised(tmp_path, monkeypatch, caplog, exc):
    def boom(fd, name, value):
        raise exc

    monkeypatch.setattr(att, "_is_macos", lambda: True)
    monkeypatch.setattr(att, "_fsetxattr", boom, raising=False)
    caplog.set_level(logging.WARNING)
    path = AttachmentStore(tmp_path).save("a.zip", b"PK")
    assert path.read_bytes() == b"PK"
    assert "karantän" in caplog.text


@pytest.mark.skipif(sys.platform != "darwin", reason="riktig xattr bara på macOS")
def test_real_quarantine_attribute_on_macos(tmp_path):
    path = AttachmentStore(tmp_path).save("Faktura.terminal", b"<plist/>")
    out = subprocess.run(
        ["/usr/bin/xattr", "-p", "com.apple.quarantine", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    flags, hex_time, agent, rest = out.split(";")
    assert flags == "0083"
    assert agent == "protonmail-mcp"
    assert rest == ""
    int(hex_time, 16)

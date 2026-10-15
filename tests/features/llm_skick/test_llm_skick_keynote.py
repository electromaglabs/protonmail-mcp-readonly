"""BDD-steg för llm_skick_keynote.feature: load_for_sending mot en riktig bilagekatalog."""
import io
import zipfile

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.attachments import AttachmentStore, load_for_sending

scenarios("llm_skick_keynote.feature")

PRIVATE_KEY = b"-----BEGIN PRIVATE KEY-----\nMIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEA\n-----END PRIVATE KEY-----\n"


def _zip(members: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "bilagor"
    path.mkdir(mode=0o700)
    return path


@pytest.fixture
def outcome():
    return {}


@given(parsers.parse('bilagekatalogen har en Keynote-presentation "{name}"'))
def keynote(root, name):
    (root / name).write_bytes(_zip({"Index/Document.iwa": b"\x00" * 64, "Metadata/Properties.plist": b"<plist/>"}))


@given(parsers.parse('bilagekatalogen har en privat nyckel "{name}"'))
def private_key(root, name):
    (root / name).write_bytes(PRIVATE_KEY)


@given(parsers.parse('bilagekatalogen har textfilen "{name}" med innehållet "{content}"'))
def text_file(root, name, content):
    (root / name).write_text(content)


@given(parsers.parse('bilagekatalogen har en Keynote-liknande fil "{name}" som innehåller en privat nyckel'))
def zip_with_key(root, name):
    (root / name).write_bytes(_zip({"nyckel.pem": PRIVATE_KEY}, compression=zipfile.ZIP_STORED))


@when(parsers.parse('filen "{name}" görs till bilaga'))
def make_attachment(root, outcome, name):
    try:
        outcome["parts"] = load_for_sending([name], AttachmentStore(root))
    except ValueError as exc:
        outcome["error"] = exc


@then(parsers.parse('ska bilagan "{name}" skapas'))
def attachment_created(outcome, name):
    assert "error" not in outcome, outcome.get("error")
    assert [part.get_filename() for part in outcome["parts"]] == [name]


@then(parsers.parse('ska bilagan vägras med ett fel som nämner "{text}"'))
def attachment_refused(outcome, text):
    assert text in str(outcome.get("error"))

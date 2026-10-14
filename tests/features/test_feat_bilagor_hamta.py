"""BDD-steg för feat_bilagor_hamta.feature (verktyget get_attachment)."""
import asyncio
import base64
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.tools.attachments import get_attachment
from tests.feat_bilagor_support import (  # noqa: F401
    attachment_env,
    base64_part,
    multipart,
    raw_message,
    text_part,
)

scenarios("feat_bilagor_hamta.feature")

FILES = {
    "faktura.pdf": ("application/pdf", b"%PDF-1.4 faktura\x00\x01\x02"),
    "anteckning.txt": ("text/plain; charset=iso-8859-1", "Räksmörgås på fredag".encode("latin-1")),
}


@pytest.fixture
def state():
    return {"mailbox": {}}


@pytest.fixture
def root(attachment_env):
    return attachment_env[0]


@pytest.fixture
def ctx(state):
    ctx = MagicMock()
    app = ctx.request_context.lifespan_context
    app.imap = AsyncMock()

    async def get_message(folder, uid):
        return state["mailbox"].get((folder, uid))

    app.imap.get_message.side_effect = get_message
    return ctx


@given(parsers.parse(
    'ett mejl med UID "{uid}" i "{folder}" med brödtext och bilagorna "{first}" och "{second}"'
))
def message_with_files(state, uid, folder, first, second):
    parts = [text_part()]
    for name in (first, second):
        ctype, data = FILES[name]
        parts.append(base64_part(ctype, f'; filename="{name}"', data))
    state["mailbox"][(folder, uid)] = raw_message(multipart(*parts))
    state["data"] = {name: FILES[name][1] for name in (first, second)}


@given(parsers.parse('ett mejl med UID "{uid}" i "{folder}" med en bilaga som heter "{name}"'))
def message_with_evil_name(state, uid, folder, name):
    data = b"export EVIL=1"
    state["mailbox"][(folder, uid)] = raw_message(
        multipart(text_part(), base64_part("application/octet-stream", f'; filename="{name}"', data))
    )
    state["data"] = {"zshrc": data}


@given(parsers.parse("att gränsen för direktläsning är {limit:d} byte"))
def inline_limit(monkeypatch, limit):
    from protonmail_mcp.config import get_settings

    monkeypatch.setenv("PROTONMAIL_ATTACHMENT_MAX_INLINE_BYTES", str(limit))
    get_settings.cache_clear()


def _fetch(ctx, state, uid, folder, index, save):
    try:
        state["result"] = asyncio.run(
            get_attachment(ctx, uid=uid, mailbox=folder, index=index, save=save)
        )
    except ValueError as exc:
        state["error"] = exc


@when(parsers.parse('jag hämtar bilaga {index:d} ur mejlet "{uid}" i "{folder}"'))
def fetch_save(ctx, state, root, index, uid, folder):
    _fetch(ctx, state, uid, folder, index, True)


@when(parsers.parse('jag hämtar bilaga {index:d} ur mejlet "{uid}" i "{folder}" utan att spara'))
def fetch_inline(ctx, state, root, index, uid, folder):
    _fetch(ctx, state, uid, folder, index, False)


@then(parsers.parse('ska filen "{name}" finnas i bilagekatalogen med bilagans innehåll'))
def saved_file(root, state, name):
    path = root / name
    assert path.is_file()
    original = name.replace(" (1)", "")
    assert path.read_bytes() == state["data"][original]


@then(parsers.parse('ska svaret ange sökvägen, storleken, typen "{ctype}" och sha256'))
def save_result(root, state, ctype):
    result = state["result"]
    data = Path(result["path"]).read_bytes()
    assert Path(result["path"]).parent == root.resolve()
    assert result["size"] == len(data)
    assert result["content_type"] == ctype
    assert result["sha256"] == hashlib.sha256(data).hexdigest()
    assert result["mailbox"] == "INBOX" and result["uid"] == "42" and result["index"] == 0


@then("ska svaret innehålla bilagan base64-kodad")
def inline_base64(state):
    result = state["result"]
    assert result["encoding"] == "base64"
    assert base64.b64decode(result["content"]) == state["data"]["faktura.pdf"]
    assert "path" not in result


@then("ska inget ha sparats i bilagekatalogen")
def nothing_saved(root):
    assert not root.exists() or not any(root.iterdir())


@then(parsers.parse('ska svaret innehålla texten "{text}"'))
def inline_text(state, text):
    assert state["result"]["encoding"] == "text"
    assert state["result"]["content"] == text


@then(parsers.parse('ska hämtningen avvisas med ett fel som nämner "{text}"'))
def rejected(state, text):
    assert "result" not in state
    assert text in str(state["error"])


@then("ska inget ha skrivits utanför bilagekatalogen")
def nothing_outside(root):
    parent = root.parent
    assert {p for p in parent.rglob("*") if p.is_file()} == {
        p for p in root.rglob("*") if p.is_file()
    }

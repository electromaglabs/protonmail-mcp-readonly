"""F13: emoji-taggsekvenserna för England, Skottland och Wales bevaras."""
import pytest

from protonmail_mcp.sanitize import injection_signals, sanitize_text


def _tags(text: str) -> str:
    return "".join(chr(0xE0000 + ord(c)) for c in text)


BLACK_FLAG = "\U0001F3F4"
CANCEL = "\U000E007F"


@pytest.mark.parametrize("code", ["gbeng", "gbsct", "gbwls"])
def test_rgi_flaggan_behalls(code):
    flag = BLACK_FLAG + _tags(code) + CANCEL
    result = sanitize_text(f"Heja {flag}!")
    assert result.text == f"Heja {flag}!"
    assert result.removed == {}


def test_flera_flaggor_i_rad_behalls():
    text = "".join(BLACK_FLAG + _tags(c) + CANCEL for c in ("gbeng", "gbsct", "gbwls"))
    assert sanitize_text(text).text == text


@pytest.mark.parametrize(
    "spec",
    ["ustx", "ignore", "gbengx", "gb", "GBENG", "gb eng"],
    ids=["texas-ej-rgi", "fritext", "for-lang", "for-kort", "versaler", "blanksteg"],
)
def test_andra_taggsekvenser_tas_bort(spec):
    text = BLACK_FLAG + _tags(spec) + CANCEL
    result = sanitize_text(text)
    assert result.text == BLACK_FLAG
    assert result.removed == {"tag": len(spec) + 1}


def test_flaggsekvens_utan_svart_flagga_tas_bort():
    result = sanitize_text("a" + _tags("gbeng") + CANCEL)
    assert result.text == "a"
    assert result.removed == {"tag": 6}


def test_flaggsekvens_utan_cancel_tas_bort():
    result = sanitize_text(BLACK_FLAG + _tags("gbeng"))
    assert result.text == BLACK_FLAG


def test_rensningen_ar_stabil_for_flaggor():
    text = "x" + BLACK_FLAG + _tags("gbsct") + CANCEL + _tags("hi") + "y"
    once = sanitize_text(text).text
    assert sanitize_text(once).text == once
    assert once == "x" + BLACK_FLAG + _tags("gbsct") + CANCEL + "y"


def test_flaggan_ger_ingen_injektionsvarning():
    assert injection_signals("Heja " + BLACK_FLAG + _tags("gbeng") + CANCEL) == []

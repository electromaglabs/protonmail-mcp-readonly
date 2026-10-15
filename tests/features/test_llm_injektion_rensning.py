"""BDD: osynliga och vilseledande tecken rensas (llm-injektion)."""
import re
import time

from pytest_bdd import given, parsers, scenarios, then, when

from protonmail_mcp.sanitize import sanitize_text

scenarios("llm_injektion_rensning.feature")


def _unescape(text: str) -> str:
    """{U+200B} i feature-filen blir tecknet U+200B (osynliga tecken syns i filen)."""
    return re.sub(r"\{U\+([0-9A-F]{4,6})\}", lambda m: chr(int(m.group(1), 16)), text)


def _tags(text: str) -> str:
    return "".join(chr(0xE0000 + ord(ch)) for ch in text)


@given(parsers.parse('en text "{visible}" följd av taggtecken som stavar "{hidden}"'), target_fixture="text")
def text_with_tags(visible, hidden):
    return visible + _tags(hidden)


@given(parsers.parse('texten "{text}"'), target_fixture="text")
def plain_text(text):
    return _unescape(text)


@given(
    parsers.parse("en text på {millions:d} miljoner tecken där vart tionde är ett nollbreddstecken"),
    target_fixture="text",
)
def long_text(millions):
    return ("abcdefghi\u200b") * (millions * 100_000)


@when("texten rensas", target_fixture="cleaned")
def clean(text):
    return sanitize_text(text)


@when("texten rensas och tiden mäts", target_fixture="cleaned")
def clean_timed(text, request):
    start = time.perf_counter()
    result = sanitize_text(text)
    request.node.elapsed = time.perf_counter() - start
    return result


@then(parsers.parse('ska den rensade texten vara "{expected}"'))
def cleaned_is(cleaned, expected):
    assert cleaned.text == _unescape(expected)


@then(parsers.parse("{count:d} tecken ska rapporteras som borttagna"))
def removed_count(cleaned, count):
    assert cleaned.count == count


@then(parsers.parse("ska det ta under {seconds:d} sekunder"))
def took_less_than(request, seconds):
    assert request.node.elapsed < seconds, f"tog {request.node.elapsed:.2f} s"

"""Rensning av avsändarstyrd text innan den når en LLM.

Allt i ett mejl (ämne, visningsnamn, brödtext, bilagenamn, HTML) styrs av
avsändaren. Tecken som är osynliga för en människa men läses av modellen är
den vanligaste platsen att gömma promptinjektion i:

- Unicode-taggtecken U+E0000–U+E007F ("ASCII-smuggling": varje ASCII-tecken
  har ett osynligt tvillingtecken, så en hel instruktion kan gömmas i ett ämne)
- nollbreddstecken (U+200B–U+200D, U+2060, U+FEFF …) som delar upp nyckelord
- bidi-styrtecken (U+202A–U+202E, U+2066–U+2069) som får människan att läsa
  texten i en annan ordning än modellen ("Trojan Source")
- följder av variationsväljare, där data kan kodas efter en emoji
- övriga formattecken (Unicode-kategori Cf) och kontrolltecken utom \\n och \\t
- orimligt långa följder av kombinationstecken ("Zalgo"), kapade vid 30 som i
  UAX #15 Stream-Safe Text Format — utan tak är NFC kvadratisk i Python 3.14

Texten normaliseras sedan till NFC. Allt görs med reguljära uttryck utan
bakåtspårning och tar linjär tid.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Synliga formattecken (Cf) som hör till texten: arabiska/syriska talmarkörer
# som ritas som tecken. Allt annat i Cf är osynligt eller styr visningen.
_VISIBLE_FORMAT = frozenset(
    [0x0600, 0x0601, 0x0602, 0x0603, 0x0604, 0x0605, 0x06DD, 0x070F, 0x0890, 0x0891, 0x08E2,
     0x110BD, 0x110CD]
)
_ZWJ = 0x200D
_TAGS = range(0xE0000, 0xE0080)
_BIDI = [*range(0x202A, 0x202F), *range(0x2066, 0x206A)]
_BIDI_MARKS = [0x200E, 0x200F, 0x061C]
# Nollbredd och tecken som ritas som tomrum utan att vara blanktecken
# (CGJ, hangul-fyllnad, khmeriska osynliga vokaler, mongoliskt vokalskiljetecken)
_ZERO_WIDTH = [0x200B, 0x200C, 0x2060, 0xFEFF, 0x180E, 0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0,
               0x17B4, 0x17B5]
_VARIATION_SELECTORS = [*range(0xFE00, 0xFE10), *range(0xE0100, 0xE01F0), *range(0x180B, 0x1810)]
# Högst så många kombinationstecken (ccc > 0) i följd (UAX #15)
_MAX_NON_STARTERS = 30


def _char_class(codepoints) -> str:
    """Teckenklass "[...]" med intervall för sorterade kodpunkter."""
    points = sorted(set(codepoints))
    parts: list[str] = []
    i = 0
    while i < len(points):
        j = i
        while j + 1 < len(points) and points[j + 1] == points[j] + 1:
            j += 1
        start, end = points[i], points[j]
        parts.append(f"\\U{start:08x}" if start == end else f"\\U{start:08x}-\\U{end:08x}")
        i = j + 1
    return "[" + "".join(parts) + "]"


def _scan() -> tuple[list[int], list[int]]:
    """Formattecken (Cf) och kombinationstecken (ccc > 0) i Pythons Unicode-
    databas. Båda finns bara i plan 0, 1 och 14, så resten genomsöks inte."""
    fmt, non_starters = [], []
    for cp in (*range(0x20000), *range(0xE0000, 0xE1000)):
        ch = chr(cp)
        if unicodedata.category(ch) == "Cf":
            fmt.append(cp)
        elif unicodedata.combining(ch):
            non_starters.append(cp)
    return fmt, non_starters


_FORMAT_ALL, _NON_STARTERS = _scan()
_HANDLED = {*_TAGS, *_BIDI, *_BIDI_MARKS, *_ZERO_WIDTH, _ZWJ}
_OTHER_FORMAT = [cp for cp in _FORMAT_ALL if cp not in _HANDLED and cp not in _VISIBLE_FORMAT]

# Tecken som får stå före och efter ZWJ i en emojisekvens (familj, regnbågsflagga)
_EMOJI = (
    "\u00a9\u00ae\u203c\u2049\u2122\u2139\u2190-\u21ff\u2300-\u23ff\u24c2\u25a0-\u27bf"
    "\u2934\u2935\u2b00-\u2bff\u3030\u303d\u3297\u3299\U0001f000-\U0001faff"
)
_ZWJ_RE = re.compile(f"(?<![{_EMOJI}\ufe0f])\u200d|\u200d(?![{_EMOJI}])")

_VS = _char_class(_VARIATION_SELECTORS)
_NS = _char_class(_NON_STARTERS)
# (kategori, mönster) i den ordning de tillämpas
_PASSES: list[tuple[str, re.Pattern[str]]] = [
    ("surrogate", re.compile("[\ud800-\udfff]")),
    ("tag", re.compile(_char_class(_TAGS))),
    ("bidi", re.compile(_char_class(_BIDI))),
    ("bidi_mark", re.compile(_char_class(_BIDI_MARKS))),
    ("zero_width", re.compile(_char_class(_ZERO_WIDTH))),
    ("zero_width", _ZWJ_RE),
    ("format", re.compile(_char_class(_OTHER_FORMAT))),
    ("control", re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f]")),
    # En ensam variationsväljare (hjärta + VS16) är legitim; en följd bär data
    ("variation_selector", re.compile(f"{_VS}{{2,}}")),
    # Kombinationstecken nummer 31 och framåt i en följd. Tecknet matchas
    # först så att bakåtblicken bara görs för kombinationstecken.
    ("combining_excess", re.compile(f"{_NS}(?<={_NS}{{{_MAX_NON_STARTERS + 1}}})")),
]
# Allt som någon pass kan ta bort — saknas det räcker NFC-kontrollen
_ANY_RE = re.compile(
    "[\ud800-\udfff\x00-\x08\x0b-\x1f\x7f-\x9f\u200d]|"
    + "|".join(
        _char_class(cps)
        for cps in (_TAGS, _BIDI, _BIDI_MARKS, _ZERO_WIDTH, _OTHER_FORMAT, _VARIATION_SELECTORS,
                    _NON_STARTERS)
    )
)
_ASCII_UNSAFE_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f]")


@dataclass(frozen=True)
class Sanitized:
    """Rensad text och antal borttagna tecken per kategori (bara de > 0).

    Kategorier: tag, bidi, bidi_mark, zero_width, format, control,
    variation_selector, combining_excess, surrogate.
    """

    text: str
    removed: dict[str, int] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return sum(self.removed.values())


def _merge(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def sanitize_text(text: str | None) -> Sanitized:
    """Ta bort osynliga och vilseledande tecken och normalisera till NFC.

    \\r\\n och ensamt \\r blir \\n utan att räknas som borttagna. \\n och \\t
    behålls. Returnerar den rensade texten och vad som togs bort.
    """
    if not text:
        return Sanitized("")
    if text.isascii() and not _ASCII_UNSAFE_RE.search(text):
        return Sanitized(text)  # vanligast: ren ASCII är redan NFC
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    removed: dict[str, int] = {}
    if _ANY_RE.search(text):
        for category, pattern in _PASSES:
            before = len(text)
            text = pattern.sub("", text)
            if n := before - len(text):  # tecken, inte träffar (följder av variationsväljare)
                removed[category] = removed.get(category, 0) + n
    if not unicodedata.is_normalized("NFC", text):
        text = unicodedata.normalize("NFC", text)
    return Sanitized(text, removed)


def clean_text(text: str | None) -> str:
    """Bara den rensade texten (se sanitize_text)."""
    return sanitize_text(text).text


# Citerad sträng (även oavslutad), <adress> eller ett ord utan avgränsare.
# Inga överlappande alternativ, så varje tecken läses högst ett par gånger.
_ADDRESS_TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"?|<[^<>]*>|[^\s<>,;"]+', re.DOTALL)


def sanitize_address_text(text: str | None) -> Sanitized:
    """Rensa en adressrad ("Anna <anna@x.se>, b@y.se") utan att röra adresserna.

    Adressdelen ändras aldrig — en rensad adress kunde peka på en annan
    mottagare. Det som står inom <…> och ord med @ utanför citattecken lämnas
    orörda; visningsnamn (även citerade) och övrig text rensas.
    """
    if not text:
        return Sanitized("")
    if text.isascii() and not _ASCII_UNSAFE_RE.search(text):
        return Sanitized(text)
    out: list[str] = []
    removed: dict[str, int] = {}
    pending_start = 0

    def flush(end: int) -> None:
        if end > pending_start:
            result = sanitize_text(text[pending_start:end])
            out.append(result.text)
            _merge(removed, result.removed)

    for m in _ADDRESS_TOKEN_RE.finditer(text):
        token = m.group()
        if token.startswith("<") or (not token.startswith('"') and "@" in token):
            flush(m.start())
            out.append(token)
            pending_start = m.end()
    flush(len(text))
    return Sanitized("".join(out), removed)

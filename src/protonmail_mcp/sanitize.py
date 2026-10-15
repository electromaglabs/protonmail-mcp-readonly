"""Rensning av avsändarstyrd text innan den når en LLM.

Allt i ett mejl (ämne, visningsnamn, brödtext, bilagenamn, HTML) styrs av
avsändaren. Tecken som är osynliga för en människa men läses av modellen är
den vanligaste platsen att gömma promptinjektion i:

- Unicode-taggtecken U+E0000–U+E007F ("ASCII-smuggling": varje ASCII-tecken
  har ett osynligt tvillingtecken, så en hel instruktion kan gömmas i ett ämne)
- nollbreddstecken (U+200B–U+200D, U+2060, U+FEFF …) som delar upp nyckelord
- bidi-styrtecken (U+202A–U+202E, U+2066–U+2069) som får människan att läsa
  texten i en annan ordning än modellen ("Trojan Source")
- variationsväljare, där data kan kodas en byte per synligt tecken; bara
  VS15/VS16 direkt efter en emoji behålls
- övriga formattecken (Unicode-kategori Cf) och kontrolltecken utom \\n och \\t
- orimligt långa följder av kombinationstecken ("Zalgo"), kapade vid 30 som i
  UAX #15 Stream-Safe Text Format — utan tak är NFC kvadratisk i Python 3.14

Texten normaliseras sedan till NFC, och rensningen upprepas tills inget
ändras (högst några varv), så att resultatet är stabilt: en andra rensning
tar aldrig bort något. Allt görs med reguljära uttryck utan bakåtspårning och
tar linjär tid.

Homoglyfer (kyrilliskt a, U+0430, för latinskt a osv.) är synliga och rensas inte.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Formattecken (Cf) enligt Unicode 16, så att även äldre Python (3.10 har
# Unicode 13) tar bort tecken som lagts till senare. Unionen med Pythons egen
# databas tas nedan.
_KNOWN_FORMAT_RANGES = [
    (0x00AD, 0x00AD), (0x0600, 0x0605), (0x061C, 0x061C), (0x06DD, 0x06DD), (0x070F, 0x070F),
    (0x0890, 0x0891), (0x08E2, 0x08E2), (0x180E, 0x180E), (0x200B, 0x200F), (0x202A, 0x202E),
    (0x2060, 0x2064), (0x2066, 0x206F), (0xFEFF, 0xFEFF), (0xFFF9, 0xFFFB), (0x110BD, 0x110BD),
    (0x110CD, 0x110CD), (0x13430, 0x1343F), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
    (0xE0001, 0xE0001), (0xE0020, 0xE007F),
]
# Default_Ignorable_Code_Point som inte är Cf: otilldelade tecken som ändå
# aldrig ritas (resten av plan 14, U+2065, U+FFF0–U+FFF8). Tas bort som format.
_IGNORABLE_UNASSIGNED = [0x2065, *range(0xFFF0, 0xFFF9), *range(0xE0080, 0xE0100),
                         *range(0xE01F0, 0xE1000)]
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
# Högst så många kombinationstecken i följd (UAX #15)
_MAX_MARKS = 30
# Högsta längd för en adress (RFC 5321 \u00a74.5.3.1.3); längre ord är inga adresser
_MAX_ADDRESS_LEN = 320
# Varv rensning + NFC tills texten är stabil (två räcker i praktiken)
_MAX_ROUNDS = 4


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


def _fast_class(codepoints) -> str:
    """Som _char_class, men snabb för tecken som inte matchar.

    re kan bara slå upp tecken i BMP i en tabell; tecken utanför BMP prövas
    mot varje intervall i tur och ordning, för varje tecken i texten. Därför
    prövas intervallen utanför BMP bara när tecknet självt ligger där.
    """
    points = set(codepoints)
    bmp = [cp for cp in points if cp <= 0xFFFF]
    astral = [cp for cp in points if cp > 0xFFFF]
    parts = [_char_class(bmp)] if bmp else []
    if astral:
        parts.append(f"(?=[\\U00010000-\\U0010ffff]){_char_class(astral)}")
    return "(?:" + "|".join(parts) + ")"


def _scan() -> tuple[list[int], list[int]]:
    """Formattecken (Cf) och kombinationstecken (kategori M eller ccc > 0) i
    Pythons Unicode-databas. Båda finns bara i plan 0, 1 och 14."""
    fmt, marks = [], []
    for cp in (*range(0x20000), *range(0xE0000, 0xE1000)):
        ch = chr(cp)
        category = unicodedata.category(ch)
        if category == "Cf":
            fmt.append(cp)
        elif category[0] == "M" or unicodedata.combining(ch):
            marks.append(cp)
    return fmt, marks


_FORMAT_SCANNED, _MARKS_SCANNED = _scan()
_FORMAT_ALL = {
    *_FORMAT_SCANNED,
    *(cp for lo, hi in _KNOWN_FORMAT_RANGES for cp in range(lo, hi + 1)),
    *_IGNORABLE_UNASSIGNED,
}
_HANDLED = {*_TAGS, *_BIDI, *_BIDI_MARKS, *_ZERO_WIDTH, _ZWJ}
_OTHER_FORMAT = [cp for cp in _FORMAT_ALL if cp not in _HANDLED and cp not in _VISIBLE_FORMAT]
_MARKS = sorted(set(_MARKS_SCANNED) - set(_VARIATION_SELECTORS))

# Tecken som får stå före VS15/VS16 och på båda sidor om ZWJ i en emojisekvens
_EMOJI = (
    "\u00a9\u00ae\u203c\u2049\u2122\u2139\u2190-\u21ff\u2300-\u23ff\u24c2\u25a0-\u27bf"
    "\u2934\u2935\u2b00-\u2bff\u3030\u303d\u3297\u3299\U0001f000-\U0001faff"
)
# Tecknet matchas först och bakåtblicken (som tar med tecknet självt) görs
# bara för väljarna och ZWJ, inte för varje tecken i texten.
_VARIATION_RE = re.compile(
    # VS1–VS14, mongoliska väljare och ideografiska varianter (IVS) har ingen
    # användning i vanlig e-post — en IVS efter varje kanji kunde bära en byte
    "[\ufe00-\ufe0d\u180b-\u180d\u180f\U000e0100-\U000e01ef]"
    # VS15/VS16 bara direkt efter en emoji eller keycap-bas (siffra + VS16 + U+20E3)
    f"|[\ufe0e\ufe0f](?<![{_EMOJI}0-9#*][\ufe0e\ufe0f])"
)
_ZWJ_RE = re.compile(f"\u200d(?<![{_EMOJI}\ufe0f]\u200d)|\u200d(?![{_EMOJI}])")
_MARK_CLASS = _fast_class(_MARKS)

# (kategori, mönster) i den ordning de tillämpas. Variationsväljarna tas före
# ZWJ, eftersom ZWJ bara får stå kvar efter en väljare som själv står kvar.
_PASSES: list[tuple[str, re.Pattern[str]]] = [
    ("surrogate", re.compile("[\ud800-\udfff]")),
    ("tag", re.compile(_char_class(_TAGS))),
    ("bidi", re.compile(_fast_class(_BIDI))),
    ("bidi_mark", re.compile(_fast_class(_BIDI_MARKS))),
    ("zero_width", re.compile(_fast_class(_ZERO_WIDTH))),
    ("format", re.compile(_char_class(_OTHER_FORMAT))),
    ("control", re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f]")),
    ("variation_selector", _VARIATION_RE),
    ("zero_width", _ZWJ_RE),
    # Kombinationstecken nummer 31 och framåt i en följd. Tecknet matchas
    # först så att bakåtblicken bara görs för kombinationstecken.
    ("combining_excess", re.compile(f"{_MARK_CLASS}(?<={_MARK_CLASS}{{{_MAX_MARKS + 1}}})")),
]
# Allt som någon pass kan ta bort — saknas det räcker NFC-kontrollen
_ANY_RE = re.compile(
    _fast_class(
        [*range(0xD800, 0xE000), *range(0x00, 0x09), *range(0x0B, 0x20), *range(0x7F, 0xA0), _ZWJ,
         *_TAGS, *_BIDI, *_BIDI_MARKS, *_ZERO_WIDTH, *_OTHER_FORMAT, *_VARIATION_SELECTORS, *_MARKS]
    )
)
_ASCII_UNSAFE_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f]")
_TAG_RE = re.compile(_char_class(_TAGS))


@dataclass(frozen=True)
class Sanitized:
    """Rensad text och antal borttagna tecken per kategori (bara de > 0).

    Kategorier: tag, bidi, bidi_mark, zero_width, format, control,
    variation_selector, combining_excess, surrogate.

    kept_in_address: tecken som annars skulle ha tagits bort men som står
    kvar för att de är en del av en adress (se sanitize_address_text).
    """

    text: str
    removed: dict[str, int] = field(default_factory=dict)
    kept_in_address: int = 0

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
    for _ in range(_MAX_ROUNDS):
        changed = False
        if _ANY_RE.search(text):
            for category, pattern in _PASSES:
                before = len(text)
                text = pattern.sub("", text)
                if n := before - len(text):  # tecken, inte träffar
                    removed[category] = removed.get(category, 0) + n
                    changed = True
        if not unicodedata.is_normalized("NFC", text):
            text = unicodedata.normalize("NFC", text)
            changed = True
        # Ett varv utan borttagning på NFC-text är stabilt. Annars ett varv
        # till: NFC eller en borttagning kan ha gjort nya grannar.
        if not changed:
            break
    return Sanitized(text, removed)


def clean_text(text: str | None) -> str:
    """Bara den rensade texten (se sanitize_text)."""
    return sanitize_text(text).text


# Citerad sträng (även oavslutad), <…> eller ett ord utan avgränsare.
# Inga överlappande alternativ, så varje tecken läses högst ett par gånger.
_ADDRESS_TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"?|<[^<>]*>|[^\s<>,;"]+', re.DOTALL)


def _is_address(token: str, followed_by: str) -> bool:
    if token.startswith('"'):
        return followed_by == "@"  # citerad lokaldel: "anna svensson"@x.se
    return "@" in token and len(token) <= _MAX_ADDRESS_LEN + 2


def sanitize_address_text(text: str | None) -> Sanitized:
    """Rensa en adressrad ("Anna <anna@x.se>, b@y.se") utan att röra adresserna.

    Adressdelen ändras inte — en rensad adress kunde peka på en annan
    mottagare. Som adress räknas <…> med @, ord med @ utanför citattecken och
    en citerad lokaldel direkt före @, högst 320 tecken. Visningsnamn (även
    citerade) och övrig text rensas.

    Undantag: Unicode-taggtecken tas bort även i adresser. De kan inte ingå i
    en adress som går att leverera till och är den vanligaste smuggelvägen.
    Andra tecken som står kvar i en adress räknas i kept_in_address.
    """
    if not text:
        return Sanitized("")
    if text.isascii() and not _ASCII_UNSAFE_RE.search(text):
        return Sanitized(text)
    out: list[str] = []
    removed: dict[str, int] = {}
    kept = 0
    pending_start = 0

    def flush(end: int) -> None:
        if end > pending_start:
            result = sanitize_text(text[pending_start:end])
            out.append(result.text)
            _merge(removed, result.removed)

    for m in _ADDRESS_TOKEN_RE.finditer(text):
        token = m.group()
        if not _is_address(token, text[m.end():m.end() + 1]):
            continue
        flush(m.start())
        token, tags = _TAG_RE.subn("", token)
        if tags:
            removed["tag"] = removed.get("tag", 0) + tags
        kept += sanitize_text(token).count
        out.append(token)
        pending_start = m.end()
    flush(len(text))
    return Sanitized("".join(out), removed, kept)

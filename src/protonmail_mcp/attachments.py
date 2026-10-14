"""Bilagekatalogen: all filåtkomst för bilagor stannar i en katalog.

Filnamn i mejl styrs av avsändaren och sökvägar till filer som ska skickas
kommer från klienten (en AI-modell). Båda behandlas som opålitliga:

- Avsändarens filnamn saneras till ett enda rent filnamn (ingen sökväg,
  inga kontroll- eller riktningstecken) innan det används på disk, och en
  befintlig fil skrivs aldrig över — en krock ger ett suffix, " (1)".
- En sökväg att skicka löses upp (symlänkar följs) och måste hamna inuti
  bilagekatalogen; path traversal, absoluta sökvägar utanför och symlänkar
  som pekar ut avvisas, liksom namn med kontrolltecken.
"""
from __future__ import annotations

import mimetypes
import os
import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Settings

# Längsta filnamn i byte (UTF-8). De flesta filsystem tillåter 255; marginalen
# räcker till kollisionssuffixet " (999)".
_MAX_NAME_BYTES = 200
_MAX_EXTENSION_CHARS = 16
_MAX_COLLISIONS = 1000
_FALLBACK_STEM = "bilaga"
# Tecken som Windows och många synkverktyg inte tål i filnamn
_RESERVED_CHARS_RE = re.compile(r'[<>:"|?*]')
# Enhetsnamn som Windows tolkar som enheter oavsett filändelse
_WINDOWS_DEVICES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)


def _is_unsafe_char(ch: str) -> bool:
    """Kontrolltecken (Cc), format-/riktningstecken som U+202E (Cf),
    radavgränsare (Zl, Zp) samt surrogat, privata och otilldelade tecken."""
    return unicodedata.category(ch) in {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}


def _extension_for(content_type: str | None) -> str:
    if content_type:
        ext = mimetypes.guess_extension(content_type.lower(), strict=False)
        if ext:
            return ext
    return ".bin"


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore")


def _strip_dots_and_space(text: str) -> str:
    """Ta bort inledande punkter (dolda filer, "..") och avslutande punkter,
    även blandat med blanktecken som " . .dold". Linjär tid — ett regex som
    [\s.]+$ blir kvadratiskt på långa serier, och namnet styrs av avsändaren."""
    start, end = 0, len(text)
    while start < end and (text[start] == "." or text[start].isspace()):
        start += 1
    while end > start and (text[end - 1] == "." or text[end - 1].isspace()):
        end -= 1
    return text[start:end]


def sanitize_filename(name: str | None, content_type: str | None = None) -> str:
    """Gör ett avsändarstyrt filnamn till ett säkert filnamn utan sökväg.

    Behåller bara sista ledet efter / eller \\, tar bort osäkra tecken,
    inledande punkter (inga dolda filer, inget "..") och avslutande punkter
    och blanksteg. Blir inget kvar används "bilaga" med en filändelse
    gissad ur content_type.
    """
    text = unicodedata.normalize("NFC", name or "")
    text = "".join(ch for ch in text if not _is_unsafe_char(ch))
    text = re.split(r"[/\\]", text)[-1]
    text = _RESERVED_CHARS_RE.sub("_", text)
    text = _strip_dots_and_space(text)
    if not text:
        return _FALLBACK_STEM + _extension_for(content_type)
    stem, dot, ext = text.rpartition(".")
    if not dot or not stem or len(ext) > _MAX_EXTENSION_CHARS:
        stem, ext = text, ""
    if stem.split(".")[0].upper() in _WINDOWS_DEVICES:
        stem = "_" + stem
    suffix = f".{ext}" if ext else ""
    stem = _truncate_utf8(stem, _MAX_NAME_BYTES - len(suffix.encode("utf-8"))).rstrip(". ")
    return (stem or _FALLBACK_STEM) + suffix


def _numbered(name: str, n: int) -> str:
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        return f"{name} ({n})"
    return f"{stem} ({n}).{ext}"


class AttachmentStore:
    """Läser och skriver bilagor, bara inuti ``root``."""

    def __init__(self, root: Path | str, max_inline_bytes: int = 1024 * 1024) -> None:
        self.root = Path(root).expanduser()
        self.max_inline_bytes = max_inline_bytes

    @classmethod
    def from_settings(cls, settings: Settings) -> AttachmentStore:
        return cls(settings.attachment_dir, max_inline_bytes=settings.attachment_max_inline_bytes)

    def _ensure_root(self) -> Path:
        """Skapa katalogen vid behov (0700) och returnera den upplöst."""
        if not self.root.exists():
            try:
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                self.root.chmod(0o700)  # mkdir påverkas av umask
            except OSError as exc:  # t.ex. en trasig symlänk eller saknad behörighet
                raise ValueError(
                    f"Bilagekatalogen {self.root} kan inte skapas: {exc.strerror or exc}"
                ) from None
        resolved = self.root.resolve()
        if not resolved.is_dir():
            raise ValueError(f"Bilagekatalogen {self.root} är ingen katalog")
        return resolved

    def _resolved_root(self) -> Path:
        try:
            resolved = self.root.resolve(strict=True)
        except (FileNotFoundError, RuntimeError):
            raise ValueError(
                f"Bilagekatalogen {self.root} finns inte. Lägg filerna som ska "
                "skickas där (PROTONMAIL_ATTACHMENT_DIR)."
            ) from None
        if not resolved.is_dir():
            raise ValueError(f"Bilagekatalogen {self.root} är ingen katalog")
        return resolved

    def save(self, filename: str | None, data: bytes, content_type: str | None = None) -> Path:
        """Spara data under ett sanerat filnamn och returnera den nya filens sökväg.

        Skriver aldrig över: finns namnet redan (även som symlänk) prövas
        "namn (1).ext", "namn (2).ext" och så vidare. Filen skapas med O_EXCL
        och O_NOFOLLOW och rättigheterna 0600.
        """
        root = self._ensure_root()
        base = sanitize_filename(filename, content_type)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        for n in range(_MAX_COLLISIONS):
            path = root / (base if n == 0 else _numbered(base, n))
            if path.parent != root:  # kan inte hända efter saneringen, men ändå
                raise ValueError("Ogiltigt filnamn för bilagan")
            try:
                fd = os.open(path, flags, 0o600)
            except FileExistsError:
                continue
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            return path
        raise ValueError(
            f"För många filer som heter {base!r} i bilagekatalogen — städa bland dem"
        )

    def resolve_existing(self, name: str) -> Path:
        """Upplöst sökväg till en befintlig vanlig fil inuti bilagekatalogen.

        ``name`` är ett filnamn eller en sökväg relativt katalogen, eller en
        absolut sökväg som pekar in i den. ~ expanderas inte.
        """
        if not name or not name.strip():
            raise ValueError("Tomt filnamn för bilaga")
        if any(_is_unsafe_char(ch) for ch in name):
            raise ValueError(f"Filnamnet {name!r} innehåller kontrolltecken")
        root = self._resolved_root()
        candidate = Path(name)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, NotADirectoryError):
            raise ValueError(f"Filen {name!r} finns inte i bilagekatalogen {root}") from None
        except (RuntimeError, OSError) as exc:  # symlänkloop m.m.
            raise ValueError(f"Filen {name!r} kan inte läsas: {exc.strerror or exc}") from None
        if resolved == root or root not in resolved.parents:
            raise ValueError(
                f"{name!r} ligger utanför bilagekatalogen {root}. Bara filer i "
                "bilagekatalogen (PROTONMAIL_ATTACHMENT_DIR) kan skickas."
            )
        if not resolved.is_file():
            raise ValueError(f"{name!r} är inte en vanlig fil")
        return resolved


def get_store() -> AttachmentStore:
    """Bilagekatalogen enligt inställningarna (PROTONMAIL_ATTACHMENT_DIR)."""
    from .config import get_settings

    return AttachmentStore.from_settings(get_settings())

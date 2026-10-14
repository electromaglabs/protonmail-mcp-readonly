"""HTML → läsbar text för e-post.

Ersätter den gamla regex-strippningen, som släppte igenom <style>/<script>,
MSO-villkorskommentarer och '>' i attributvärden, inte avkodade entiteter och
gjorde HTML på en rad till ett enda textblock. Bygger på stdlib html.parser.
"""
import html
import re
from html.parser import HTMLParser

# Innehåll som aldrig visas för läsaren
_SKIP = {"style", "script", "template", "title"}
# Ger radbrytning före och efter
_BLOCK = {
    "address", "article", "aside", "caption", "center", "dd", "div", "dl", "dt",
    "fieldset", "figcaption", "figure", "footer", "form", "header", "li", "main",
    "nav", "ol", "section", "table", "tbody", "tfoot", "thead", "tr", "ul",
}
# Ger tom rad före och efter
_PARAGRAPH = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "pre", "blockquote"}
# Hör hemma i <head>; allt annat stänger head, som i en webbläsare (K5)
_HEAD_TAGS = {
    "html", "head", "title", "meta", "link", "style", "script", "base", "noscript", "template",
}
_WS_RE = re.compile(r"\s+")
# Fler citatnivåer än så visas som tio — annars kan djupt nästlade
# <blockquote> blåsa upp utdata kvadratiskt mot indata
_MAX_QUOTE_PREFIX = 10


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # entiteter avkodas i handle_data
        self.lines: list[tuple[int, list[str]]] = []  # (citatdjup, textfragment)
        self.open = False  # är lines[-1] en pågående rad?
        self.blank_before_next = False
        self.skip = 0
        self.in_head = False
        self.pre = 0
        self.quote = 0

    # --- radhantering ---------------------------------------------------
    def _start_line(self) -> None:
        if self.blank_before_next and self.lines:
            depth = min(self.lines[-1][0], self.quote)
            self.lines.append((depth, []))
        self.blank_before_next = False
        self.lines.append((self.quote, []))
        self.open = True

    def _end_line(self) -> None:
        self.open = False

    def _paragraph(self) -> None:
        self._end_line()
        self.blank_before_next = True

    def _append(self, text: str) -> None:
        if not self.open:
            if not text.strip():
                return  # blanktecken mellan block öppnar ingen rad
            self._start_line()
            if not self.pre:
                text = text.lstrip()
        fragments = self.lines[-1][1]
        if not self.pre and text.startswith(" ") and fragments and fragments[-1].endswith(" "):
            text = text[1:]
        if text:
            fragments.append(text)  # lista + join: += på str blir kvadratiskt

    # --- HTMLParser-hooks -------------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self.in_head = True
        elif tag == "body" or tag not in _HEAD_TAGS:
            self.in_head = False  # även när </head> och <body> saknas
        if tag in _SKIP:
            self.skip += 1
        if self.skip or self.in_head:
            return
        if tag == "br":
            if not self.open:
                self._start_line()
            self._end_line()
        elif tag in _PARAGRAPH:
            self._paragraph()
            if tag == "blockquote":
                self.quote += 1
            elif tag == "pre":
                self.pre += 1
        elif tag in _BLOCK:
            self._end_line()
            if tag == "li":
                self._append("- ")
        elif tag in ("td", "th") and self.open:
            self._append(" ")

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or self.in_head:
            return
        if tag in _PARAGRAPH:
            if tag == "blockquote":
                self.quote = max(0, self.quote - 1)
            elif tag == "pre":
                self.pre = max(0, self.pre - 1)
            self._paragraph()
        elif tag in _BLOCK:
            self._end_line()

    def handle_data(self, data):
        if self.in_head and not self.skip and data.strip():
            self.in_head = False  # text stänger också ett ostängt head
        if self.skip or self.in_head:
            return
        if self.pre:
            first, *rest = data.split("\n")
            self._append(first)
            for piece in rest:
                self._end_line()
                self._start_line()
                self._append(piece)
            return
        self._append(_WS_RE.sub(" ", data))

    # Kommentarer (inkl. <!--[if mso]>…<![endif]-->) och deklarationer ignoreras
    # av HTMLParser som standard.

    def text(self) -> str:
        rendered: list[str] = []
        for depth, fragments in self.lines:
            line = "".join(fragments)
            if line != "-- ":  # signaturavgränsaren (RFC 3676) behåller sitt blanksteg
                line = line.rstrip()
            prefix = "> " * min(depth, _MAX_QUOTE_PREFIX)
            rendered.append(prefix + line if line else prefix.rstrip())
        # Inga inledande/avslutande tomrader och högst en tomrad i följd
        out: list[str] = []
        for line in rendered:
            if not line.strip("> ") and (not out or not out[-1].strip("> ")):
                continue
            out.append(line)
        while out and not out[-1].strip("> "):
            out.pop()
        return "\n".join(out)


def html_to_text(markup: str) -> str:
    """Gör om HTML till läsbar text: hoppar över style/script/head och
    kommentarer, ger radbrytningar för blockelement, citerar blockquote med
    "> " och avkodar entiteter."""
    if not markup:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:
        return html.unescape(re.sub(r"<[^>]+>", "", markup)).strip()
    return parser.text()

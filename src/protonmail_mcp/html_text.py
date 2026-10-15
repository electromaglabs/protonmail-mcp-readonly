"""HTML → läsbar text för e-post.

Ersätter den gamla regex-strippningen, som släppte igenom <style>/<script>,
MSO-villkorskommentarer och '>' i attributvärden, inte avkodade entiteter och
gjorde HTML på en rad till ett enda textblock. Bygger på stdlib html.parser.
"""
import html
import re
from dataclasses import dataclass, field
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
# Element utan innehåll (inget sluttagg), som aldrig kan gömma text
_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
    "track", "wbr",
}
# Starttaggar som implicit stänger ett öppet element (HTML:s optional end tags)
_IMPLIED_END = {
    "p": _PARAGRAPH | _BLOCK,
    "li": {"li"},
    "dt": {"dt", "dd"},
    "dd": {"dt", "dd"},
    "td": {"td", "th", "tr"},
    "th": {"td", "th", "tr"},
    "tr": {"tr"},
    "option": {"option"},
}
# Högst så många nästlade element med font-size/visibility/color/bakgrund följs;
# djupare nästling ignoreras, så varje tagg kostar högst så mycket
_MAX_STYLE_STACK = 40
_FONT_SIZE_RE = re.compile(r"font-size:([0-9]*\.?[0-9]+)(px|pt|em|rem|%)?")
_OPACITY_RE = re.compile(r"(?:^|;)opacity:([0-9]*\.?[0-9]+)(%)?")
_VISIBILITY_RE = re.compile(r"(?:^|;)visibility:(hidden|collapse|visible)")
_COLOR_RE = re.compile(r"(?:^|;)color:([^;]+)")
_BACKGROUND_RE = re.compile(r"(?:^|;)background(?:-color)?:([^;]+)")
_WHITE_RE = re.compile(
    r"(?:white|#fff|#f[ef]f[ef]f[ef]|rgba?\(25[0-5],25[0-5],25[0-5](?:,[0-9.]+)?\))(?:!important)?$"
)


def _style(attrs) -> str:
    """style-attributet i gemener utan blanktecken ("display : none" → "display:none")."""
    for name, value in attrs:
        if name == "style" and value:
            return "".join(value.lower().split())
    return ""


def _hard_hidden(attrs, style: str) -> str | None:
    """Skälet till att elementet och allt i det är osynligt, som inget
    barnelement kan ändra på (display:none, opacity:0 …), eller None."""
    if any(name == "hidden" for name, _ in attrs):
        return "hidden"
    if not style:
        return None
    if "display:none" in style:
        return "display:none"
    if "mso-hide:all" in style:
        return "mso-hide:all"
    if (m := _OPACITY_RE.search(style)) and float(m.group(1)) == 0:
        return "opacity:0"
    if "overflow:hidden" in style and re.search(r"(?:^|;)(?:max-)?height:0(?:px)?(?:;|$|!)", style):
        return "max-height:0"
    return None


def _soft_style(attrs, style: str) -> dict[str, bool]:
    """Ärvda egenskaper som ett barnelement kan ändra: font-size 0,
    visibility, vit textfärg och bakgrund (True = ljus eller ingen)."""
    props: dict[str, bool] = {}
    if style:
        if m := _FONT_SIZE_RE.search(style):
            size, unit = float(m.group(1)), m.group(2)
            props["font_zero"] = size == 0 or (unit in ("px", "pt") and size < 1)
        if m := _VISIBILITY_RE.search(style):
            props["vis_hidden"] = m.group(1) != "visible"
        if m := _COLOR_RE.search(style):
            props["white"] = bool(_WHITE_RE.match(m.group(1)))
        if m := _BACKGROUND_RE.search(style):
            props["light_bg"] = bool(_WHITE_RE.match(m.group(1))) or m.group(1) in ("none", "transparent")
    for name, value in attrs:
        if name == "bgcolor" and value:
            props["light_bg"] = bool(_WHITE_RE.match("".join(value.lower().split())))
    return props


@dataclass
class HtmlText:
    """Resultatet av html_to_text_report.

    text: den synliga texten. hidden_text: text i gömda element (visas inte
    för läsaren och ingår inte i text). hidden_elements: antal gömda element
    (yttersta), hidden_reasons: antal per skäl. white_text: vit text utan
    bakgrundsfärg (syns inte på vit bakgrund men ingår i text).
    """

    text: str
    hidden_text: str = ""
    hidden_elements: int = 0
    hidden_reasons: dict[str, int] = field(default_factory=dict)
    white_text: str = ""

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
        # Gömt innehåll: hard = (taggnamn, djup) för ett element som display:none
        self.hard: list = [None, 0]
        # Ärvda stilar: [taggnamn, djup, egenskaper]; se _soft_style
        self.styles: list[list] = []
        self.style_tags: dict[str, int] = {}  # taggnamn → antal poster i styles
        self.soft_hidden = False
        self.white = False
        self.hidden_parts: list[str] = []
        self.white_parts: list[str] = []
        self.hidden_elements = 0
        self.hidden_reasons: dict[str, int] = {}

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

    # --- gömt innehåll ----------------------------------------------------
    def _hide(self, reason: str) -> None:
        self.hidden_elements += 1
        self.hidden_reasons[reason] = self.hidden_reasons.get(reason, 0) + 1

    def _restyle(self) -> None:
        """Räkna om de ärvda stilarna: det innersta elementet som sätter en
        egenskap gäller."""
        found: dict[str, bool] = {}
        for _, _, props in reversed(self.styles):
            for key, value in props.items():
                found.setdefault(key, value)
        self.soft_hidden = found.get("font_zero", False) or found.get("vis_hidden", False)
        self.white = found.get("white", False) and found.get("light_bg", True)

    def _close_tracked(self, tag: str) -> None:
        """Ett sluttagg (äkta eller underförstått) för de spårade elementen."""
        if self.hard[0] == tag:
            self.hard[1] -= 1
            if self.hard[1] == 0:
                self.hard = [None, 0]
        if not self.style_tags.get(tag):
            return
        outermost = None
        for i, entry in enumerate(self.styles):
            if entry[0] == tag:
                entry[1] -= 1
                if entry[1] == 0 and outermost is None:
                    outermost = i
        if outermost is not None:
            for entry in self.styles[outermost:]:  # allt innanför stängs också
                self.style_tags[entry[0]] -= 1
            del self.styles[outermost:]
            self._restyle()

    def _track_start(self, tag: str, attrs) -> None:
        for open_tag, closers in _IMPLIED_END.items():
            if tag in closers and (self.hard[0] == open_tag or self.style_tags.get(open_tag)):
                self._close_tracked(open_tag)
        if tag in _VOID:
            return
        if self.hard[0] is not None:
            if tag == self.hard[0]:
                self.hard[1] += 1
            return  # inget i ett gömt element kan bli synligt
        if self.style_tags.get(tag):
            for entry in self.styles:
                if entry[0] == tag:
                    entry[1] += 1
        style = _style(attrs)
        reason = _hard_hidden(attrs, style)
        if reason:
            self.hard = [tag, 1]
            self._hide(reason)
            return
        props = _soft_style(attrs, style)
        if props and len(self.styles) < _MAX_STYLE_STACK:
            was_hidden = self.soft_hidden
            self.styles.append([tag, 1, props])
            self.style_tags[tag] = self.style_tags.get(tag, 0) + 1
            self._restyle()
            if self.soft_hidden and not was_hidden:
                self._hide("font-size:0" if props.get("font_zero") else "visibility:hidden")

    def _visible(self) -> bool:
        return self.hard[0] is None and not self.soft_hidden

    # --- HTMLParser-hooks -------------------------------------------------
    def handle_starttag(self, tag, attrs):
        self._track_start(tag, attrs)
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
        self._close_tracked(tag)
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
        if not self._visible():
            if data.strip():
                self.hidden_parts.append(data)
            return
        if self.white and data.strip():
            self.white_parts.append(data)
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


def _joined(parts: list[str]) -> str:
    return " ".join(" ".join(parts).split())


def html_to_text_report(markup: str) -> HtmlText:
    """Som html_to_text, men rapporterar också gömt innehåll och vit text.

    Gömt är element med display:none, visibility:hidden, font-size 0 (eller
    under 1px/1pt), opacity 0, mso-hide:all, max-height/height 0 med
    overflow:hidden och hidden-attributet. Gömd text ingår inte i text —
    läsaren ser den inte, och då ska inte heller modellen läsa den.
    Bara inline-stil räknas; regler i <style> tolkas inte.
    """
    if not markup:
        return HtmlText("")
    parser = _TextExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:
        return HtmlText(html.unescape(re.sub(r"<[^>]+>", "", markup)).strip())
    return HtmlText(
        text=parser.text(),
        hidden_text=_joined(parser.hidden_parts),
        hidden_elements=parser.hidden_elements,
        hidden_reasons=dict(parser.hidden_reasons),
        white_text=_joined(parser.white_parts),
    )


def html_to_text(markup: str) -> str:
    """Gör om HTML till läsbar text: hoppar över style/script/head,
    kommentarer och gömda element, ger radbrytningar för blockelement,
    citerar blockquote med "> " och avkodar entiteter."""
    return html_to_text_report(markup).text

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
# Starttagg → de öppna element den stänger (inversen av _IMPLIED_END)
_CLOSED_BY: dict[str, frozenset[str]] = {}
for _open, _closers in _IMPLIED_END.items():
    for _closer in _closers:
        _CLOSED_BY[_closer] = _CLOSED_BY.get(_closer, frozenset()) | {_open}
# Element som avgränsar sökningen efter ett implicit stängt element: ett <li>
# i en inre lista stänger inte den yttre listans <li>, en <td> i en inre
# tabell inte den yttre tabellens cell (HTML:s "scope")
_SCOPE_BOUNDARY = frozenset({"table", "ul", "ol", "dl", "td", "th", "caption", "button", "html", "body"})
# Så djupt i stacken söks ett implicit stängt element — längre ned räknas det
# som inte öppet, så att varje starttagg kostar högst så mycket
_MAX_IMPLIED_SCAN = 64
_SIZE_RE = re.compile(r"([0-9]*\.?[0-9]+)(px|pt|em|rem|%)?$")
_ZERO_LENGTH_RE = re.compile(r"0(?:\.0*)?(?:px|pt|em|rem|%)?$")
_WHITE_RE = re.compile(r"(?:white|#fff|#f[ef]f[ef]f[ef]|rgba?\(25[0-5],25[0-5],25[0-5](?:,[0-9.]+)?\))$")
_IMPORTANT_RE = re.compile(r"!\s*important\s*$")


def _strip_comments(text: str) -> str:
    """Ta bort /* … */ (en oavslutad kommentar slukar resten). Linjär tid."""
    if "/*" not in text:
        return text
    out: list[str] = []
    pos = 0
    while (start := text.find("/*", pos)) != -1:
        out.append(text[pos:start])
        end = text.find("*/", start + 2)
        if end == -1:
            return "".join(out)
        pos = end + 2
    out.append(text[pos:])
    return "".join(out)


def _declarations(style: str) -> dict[str, tuple[str, bool]]:
    """CSS-deklarationer → {egenskap: (värde, !important)}, i gemener och
    med blanktecken hopslagna. Som i en webbläsare gäller den sista
    deklarationen, utom att !important vinner över en senare utan."""
    out: dict[str, tuple[str, bool]] = {}
    for decl in _strip_comments(style.lower()).split(";"):
        name, sep, value = decl.partition(":")
        name = name.strip()
        if not sep or not name:
            continue
        value, important = _IMPORTANT_RE.subn("", value)
        value = " ".join(value.split())
        if name not in out or important or not out[name][1]:
            out[name] = (value, bool(important))
    return out


def _style(attrs) -> dict[str, str]:
    """style-attributets deklarationer som {egenskap: värde} (se _declarations)."""
    for name, value in attrs:
        if name == "style" and value:
            return {k: v for k, (v, _) in _declarations(value).items()}
    return {}


def _compact(value: str) -> str:
    return value.replace(" ", "")


def _number(value: str) -> float | None:
    try:
        return float(value.rstrip("%"))
    except ValueError:
        return None


def _hard_hidden(attrs, style: dict[str, str]) -> str | None:
    """Skälet till att elementet och allt i det är osynligt, som inget
    barnelement kan ändra på (display:none, opacity:0 …), eller None."""
    if any(name == "hidden" for name, _ in attrs):
        return "hidden"
    if not style:
        return None
    if style.get("display") == "none":
        return "display:none"
    if style.get("mso-hide") == "all":
        return "mso-hide:all"
    if (opacity := style.get("opacity")) is not None and _number(opacity) == 0:
        return "opacity:0"
    if style.get("overflow") == "hidden" and any(
        _ZERO_LENGTH_RE.match(style.get(prop, "x")) for prop in ("height", "max-height")
    ):
        return "max-height:0"
    return None


def _soft_style(attrs, style: dict[str, str]) -> dict[str, bool]:
    """Ärvda egenskaper som ett barnelement kan ändra: font-size 0,
    visibility, vit textfärg och bakgrund (True = ljus eller ingen)."""
    props: dict[str, bool] = {}
    if style:
        if (m := _SIZE_RE.match(style.get("font-size", ""))):
            size, unit = float(m.group(1)), m.group(2)
            props["font_zero"] = size == 0 or (unit in ("px", "pt") and size < 1)
        if (visibility := style.get("visibility")) in ("hidden", "collapse", "visible"):
            props["vis_hidden"] = visibility != "visible"
        if "color" in style:
            props["white"] = bool(_WHITE_RE.match(_compact(style["color"])))
        background = style.get("background-color", style.get("background"))
        if background is not None:
            background = _compact(background)
            props["light_bg"] = bool(_WHITE_RE.match(background)) or background in ("none", "transparent")
    for name, value in attrs:
        if name == "bgcolor" and value:
            props["light_bg"] = bool(_WHITE_RE.match("".join(value.lower().split())))
    return props


# Ärvt tillstånd för ett öppet element:
# (gömt för gott, font-size 0, visibility:hidden, vit text, ljus/ingen bakgrund)
_ROOT = (False, False, False, False, True)


def _visible_state(state: tuple) -> bool:
    return not (state[0] or state[1] or state[2])


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
        # Öppna element som (taggnamn, tillstånd); tillståndet är det ärvda
        # (se _State) och beräknas ur förälderns när elementet öppnas, så en
        # tagg kostar O(1) oavsett djup. stack_tags räknar taggnamn i stacken.
        self.stack: list[tuple[str, tuple]] = []
        self.stack_tags: dict[str, int] = {}
        self.state = _ROOT
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

    def _pop_to(self, index: int) -> None:
        """Stäng elementet på plats index och allt innanför det."""
        for tag, _ in self.stack[index:]:
            self.stack_tags[tag] -= 1
        del self.stack[index:]
        self.state = self.stack[-1][1] if self.stack else _ROOT

    def _close_tracked(self, tag: str) -> None:
        """Ett sluttagg: stäng närmaste öppna element med namnet och allt
        innanför (som en webbläsare gör med ostängda barn). Ett sluttagg
        utan öppet element ignoreras. Amorterat O(1): varje element stängs
        en gång."""
        if not self.stack_tags.get(tag):
            return
        index = len(self.stack) - 1
        while self.stack[index][0] != tag:
            index -= 1
        self._pop_to(index)

    def _close_implied(self, tag: str) -> None:
        """Starttaggar som stänger öppna element (<p> före ett block, <td>
        före nästa cell …), inom samma "scope" och högst _MAX_IMPLIED_SCAN
        element ned."""
        closes = _CLOSED_BY.get(tag)
        if not closes or not any(self.stack_tags.get(t) for t in closes):
            return
        target = None
        for index in range(len(self.stack) - 1, max(-1, len(self.stack) - 1 - _MAX_IMPLIED_SCAN), -1):
            open_tag = self.stack[index][0]
            if open_tag in closes:
                target = index
            elif open_tag in _SCOPE_BOUNDARY:
                break
        if target is not None:
            self._pop_to(target)

    def _track_start(self, tag: str, attrs) -> None:
        self._close_implied(tag)
        if tag in _VOID:
            return
        parent = self.state
        hard, font_zero, vis_hidden, white, light_bg = parent
        reason = None
        if not hard:
            style = _style(attrs)
            reason = _hard_hidden(attrs, style)
            if reason:
                hard = True
            else:
                props = _soft_style(attrs, style)
                font_zero = props.get("font_zero", font_zero)
                vis_hidden = props.get("vis_hidden", vis_hidden)
                white = props.get("white", white)
                light_bg = props.get("light_bg", light_bg)
                if (font_zero or vis_hidden) and not (parent[1] or parent[2]):
                    reason = "font-size:0" if font_zero and props.get("font_zero") else "visibility:hidden"
            if reason and _visible_state(parent):
                self._hide(reason)
        state = (hard, font_zero, vis_hidden, white, light_bg)
        self.stack.append((tag, state))
        self.stack_tags[tag] = self.stack_tags.get(tag, 0) + 1
        self.state = state

    def _visible(self) -> bool:
        return _visible_state(self.state)

    # --- HTMLParser-hooks -------------------------------------------------
    def handle_startendtag(self, tag, attrs):
        # "/>" gäller bara tomma element (och SVG/MathML); <div/> är en
        # vanlig starttagg i HTML, som webbläsaren håller öppen
        self.handle_starttag(tag, attrs)
        if tag in _VOID:
            self.handle_endtag(tag)

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
        if self.state[3] and self.state[4] and data.strip():
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
